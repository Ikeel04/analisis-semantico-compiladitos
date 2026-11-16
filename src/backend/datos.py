"""
Manejadores de datos compuestos (parte 3): arreglos, objetos, herencia y
cadenas en tiempo de ejecución.

`registrar(traductor)` agrega a `traductor.manejadores` los cuádruplos de
arreglos y objetos y reemplaza los puntos de extensión `concatenar`,
`operando_especial`, `asignar_especial` e `imprimir_especial`. También envuelve
`==` / `!=` para comparar cadenas por contenido.

Memoria (heap con `sbrk`, que MARS entrega en ceros):

    arreglo:  [longitud][e0][e1]...      palabras de 4 bytes; el puntero
                                         apunta a la longitud
    objeto:   atributos con el offset de memoria.py (los heredados primero);
              los boolean ocupan 1 byte (lbu/sb)
    cadena:   bytes terminados en 0 (.asciiz o reservada con sbrk)

| TAC               | MIPS                                                    |
|-------------------|---------------------------------------------------------|
| `t = newarray n`  | `sbrk 4·(n+1)`, `sw n, 0(t)`                            |
| `t = a[i]`        | null → `__error_null`; `0 ≤ i < len` → `__error_indice`; `lw t, 4+4i(a)` |
| `a[i] = v`        | mismas verificaciones; `sw v, 4+4i(a)`                  |
| `t = length a`    | `lw t, 0(a)`                                            |
| `t = new C`       | `sbrk` del tamaño de `C`                                |
| `t = o.campo`     | `lw`/`lbu t, offset(o)`                                 |
| `o.campo = v`     | `sw`/`sb v, offset(o)`                                  |
| `obj+N` (método)  | `lw aux, <receptor>($fp)` y `lw`/`lbu aux, N(aux)`      |
| `t = a + b` (str) | `jal __concat`                                          |
| `t = a == b` (str)| `jal __strcmp`                                          |

Registros: los operandos los pone el asignador (o `$a2`/`$a3`/`$a0` si son
literales); para direcciones intermedias se usa solo `$a1`. `$v1` NO se toca:
la parte 2 lo usa como puntero de la pila de try/catch. Las rutinas de soporte
solo modifican `$a0`–`$a3` y `$v0`; si necesitan más registros los guardan en
la pila, así el asignador no pierde nada al llamarlas.
"""

from __future__ import annotations

import tac as T
from memoria import alinear, tamano_de
from tipos import BOOLEANO, CADENA, ENTERO, FLOTANTE, NULO, es_byte, tipo_literal
from unidades import definicion, es_direccion, es_nombre

# Rutinas de soporte (etiquetas internas con prefijo __L, ver extensiones.py).
STRLEN = "__strlen"
CONCAT = "__concat"
STRCMP = "__strcmp"
INT_A_CADENA = "__int_a_cadena"
IMPRIMIR_ARREGLO = "__imprimir_arreglo"
ERROR_OBJETO_NULL = "__error_objeto_null"

# Tipo de elemento para __imprimir_arreglo.
_CLASE_ELEMENTO = {ENTERO: 0, BOOLEANO: 1, CADENA: 2}


# ----------------------------------------------------------------------
# Distribución de los objetos
# ----------------------------------------------------------------------

def construir_atributos(tipos) -> dict:
    """clase -> {campo: (offset, tipo)}, con los atributos heredados.

    Repite el cálculo de memoria.py (_layout_de_clase): los atributos del padre
    van primero y cada uno se alinea a su tamaño. Así un Perro se puede usar
    donde se espera un Animal y `obj+N` coincide con el offset de la tabla."""
    calculados: dict = {}
    tamanos: dict = {}

    def layout(clase, visitando=frozenset()):
        if clase in calculados:
            return calculados[clase], tamanos[clase]
        mapa, offset = {}, 0
        padre = tipos.padres.get(clase)
        if padre in tipos.atributos and padre not in visitando:
            heredados, offset = layout(padre, visitando | {clase})
            mapa.update(heredados)
        for campo, tipo in tipos.atributos.get(clase, {}).items():
            tamano = tamano_de(tipo)
            offset = alinear(offset, tamano)
            mapa[campo] = (offset, tipo)
            offset += tamano
        calculados[clase], tamanos[clase] = mapa, offset
        return mapa, offset

    for clase in tipos.atributos:
        layout(clase)
    return calculados


def _clase_de_funcion(nombre_funcion, clases):
    """'Perro.hablar' -> 'Perro' (también para funciones anidadas en métodos)."""
    partes = (nombre_funcion or "").split(".")
    for corte in range(len(partes) - 1, 0, -1):
        candidato = ".".join(partes[:corte])
        if candidato in clases:
            return candidato
    return None


def _offset_obj(operando) -> int:
    return int(operando.split("+")[1])


class Datos:
    """Estado y manejadores de la parte 3 (uno por traductor)."""

    def __init__(self, traductor):
        self.tr = traductor
        self.atributos = construir_atributos(traductor.tipos)

    @property
    def mips(self):
        return self.tr.mips

    # ------------------------------------------------------------------
    # Tipos de obj+N
    # ------------------------------------------------------------------

    def campo_por_offset(self, clase, offset):
        for campo, (off, tipo) in self.atributos.get(clase, {}).items():
            if off == offset:
                return campo, tipo
        return None, None

    def tipo_obj(self, operando, funcion):
        clase = _clase_de_funcion(funcion, self.atributos)
        if clase is None:
            return None
        return self.campo_por_offset(clase, _offset_obj(operando))[1]

    def envolver_tipos(self) -> None:
        """InferenciaTipos no conoce `obj+N`: se agrega aquí, así el traductor
        sabe que `obj+0` es string (concatenar) o boolean (sb/lbu, imprimir)."""
        original = self.tr.tipos.tipo_de

        def tipo_de(operando, funcion, temporales):
            if isinstance(operando, str) and operando.startswith("obj+"):
                return self.tipo_obj(operando, funcion)
            return original(operando, funcion, temporales)

        self.tr.tipos.tipo_de = tipo_de

    # ------------------------------------------------------------------
    # Excepciones
    # ------------------------------------------------------------------

    def _dentro_de_try(self) -> bool:
        profundidad = 0
        unidad = self.tr.unidad
        for _, c in unidad.instrucciones[:self.tr.pos]:
            if c.op == T.COMENTARIO and isinstance(c.arg1, str):
                partes = c.arg1.split()
                if len(partes) == 2 and partes[0] == "try":
                    profundidad += 1
                elif len(partes) == 3 and partes[:2] == ["fin", "try"]:
                    profundidad -= 1
        return profundidad > 0

    def antes_de_verificar(self) -> None:
        """Si la instrucción puede saltar a un catch de esta misma unidad, las
        variables que solo están en registro se guardan antes: el catch las
        lee de memoria (empieza un bloque nuevo)."""
        if self._dentro_de_try():
            self.tr.asignador.guardar_sucios(es_direccion, "antes de verificar (try)")

    def verificar_no_nulo(self, registro, rutina="__error_null") -> None:
        if registro == "$zero":
            self.mips.emitir("j", rutina, comentario="referencia null")
        else:
            self.mips.emitir("beqz", registro, rutina, comentario="¿null?")

    # ------------------------------------------------------------------
    # Arreglos
    # ------------------------------------------------------------------

    def nuevo_arreglo(self, c) -> None:
        tamano = str(c.arg1)
        if tipo_literal(tamano) == ENTERO:
            self.mips.emitir("li", "$a0", 4 * (int(tamano) + 1),
                             comentario=f"{tamano} elementos + longitud")
            self.mips.emitir("li", "$v0", 9)
            self.mips.emitir("syscall", comentario="sbrk")
            destino = self.tr._destino(c.resultado)
            self.mips.emitir("move", destino, "$v0")
            if int(tamano) != 0:
                self.mips.emitir("li", "$a1", int(tamano))
                self.mips.emitir("sw", "$a1", f"0({destino})", comentario="longitud")
        else:
            n = self.tr.registro_de(tamano, auxiliar="$a2")
            self.mips.emitir("addiu", "$a0", n, 1)
            self.mips.emitir("sll", "$a0", "$a0", 2)
            self.mips.emitir("li", "$v0", 9)
            self.mips.emitir("syscall", comentario="sbrk")
            destino = self.tr._destino(c.resultado, [(tamano, n)], {n})
            self.mips.emitir("sw", n, "0($v0)", comentario="longitud")
            self.mips.emitir("move", destino, "$v0")
        self.tr.escribir(c.resultado, destino)

    def _longitud_conocida(self, nombre):
        """Si `nombre` viene de un `newarray n` (n literal) en este mismo bloque
        y no se redefinió, su longitud es n: un índice literal menor que n no
        necesita verificación (así se llenan los literales [1, 2, 3])."""
        for _, c in reversed(self.tr.unidad.instrucciones[:self.tr.pos]):
            if c.op in (T.ETIQUETA, T.LLAMAR):
                return None
            if definicion(c) == nombre:
                if c.op == T.NUEVO_ARREGLO and tipo_literal(str(c.arg1)) == ENTERO:
                    return int(c.arg1)
                return None
        return None

    def _direccion_elemento(self, arreglo, indice, r_indice=None, nombre=None) -> str:
        """Verifica null y límites y devuelve la dirección base `D(r)` del
        elemento (solo usa $a1 como auxiliar)."""
        if tipo_literal(indice) == ENTERO and int(indice) >= 0:
            k = int(indice)
            conocida = self._longitud_conocida(nombre) if nombre else None
            if conocida is not None and k < conocida:
                return f"{4 + 4 * k}({arreglo})"
            self.verificar_no_nulo(arreglo)
            self.mips.emitir("lw", "$a1", f"0({arreglo})", comentario="longitud")
            self.mips.emitir("sltiu", "$a1", "$a1", k + 1)
            self.mips.emitir("bnez", "$a1", "__error_indice", comentario=f"¿{k} >= longitud?")
            return f"{4 + 4 * k}({arreglo})"
        self.verificar_no_nulo(arreglo)
        if r_indice is None:
            r_indice = self.tr.registro_de(indice, protegidos={arreglo}, auxiliar="$a3")
        self.mips.emitir("lw", "$a1", f"0({arreglo})", comentario="longitud")
        self.mips.emitir("sltu", "$a1", r_indice, "$a1",
                         comentario="0 <= i < longitud (sin signo)")
        self.mips.emitir("beqz", "$a1", "__error_indice")
        self.mips.emitir("sll", "$a1", r_indice, 2)
        self.mips.emitir("addu", "$a1", "$a1", arreglo)
        return "4($a1)"

    def leer_indice(self, c) -> None:                 # t = a[i]
        arreglo, indice = c.arg1, str(c.arg2)
        r_arreglo = self.tr.registro_de(arreglo, auxiliar="$a2")
        operandos, protegidos = [(arreglo, r_arreglo)], {r_arreglo}
        r_indice = None
        if es_nombre(indice):
            r_indice = self.tr.registro_de(indice, protegidos={r_arreglo}, auxiliar="$a3")
            operandos.append((indice, r_indice))
            protegidos.add(r_indice)
        destino = self.tr._destino(c.resultado, operandos, protegidos)
        self.antes_de_verificar()
        direccion = self._direccion_elemento(r_arreglo, indice, r_indice, arreglo)
        self.mips.emitir("lw", destino, direccion)
        self.tr.escribir(c.resultado, destino)

    def escribir_indice(self, c) -> None:             # a[i] = v
        indice, valor, arreglo = str(c.arg1), str(c.arg2), c.resultado
        r_arreglo = self.tr.registro_de(arreglo, auxiliar="$a2")
        protegidos, r_indice = {r_arreglo}, None
        if es_nombre(indice):
            r_indice = self.tr.registro_de(indice, protegidos=protegidos, auxiliar="$a3")
            protegidos.add(r_indice)
        r_valor = self.tr.registro_de(valor, protegidos=protegidos, auxiliar="$a0")
        self.antes_de_verificar()
        direccion = self._direccion_elemento(r_arreglo, indice, r_indice, arreglo)
        self.mips.emitir("sw", r_valor, direccion)

    def longitud(self, c) -> None:                    # t = length a
        r_arreglo = self.tr.registro_de(c.arg1, auxiliar="$a2")
        destino = self.tr._destino(c.resultado, [(c.arg1, r_arreglo)], {r_arreglo})
        self.antes_de_verificar()
        self.verificar_no_nulo(r_arreglo)
        self.mips.emitir("lw", destino, f"0({r_arreglo})", comentario="length")
        self.tr.escribir(c.resultado, destino)

    # ------------------------------------------------------------------
    # Objetos y herencia
    # ------------------------------------------------------------------

    def nuevo_objeto(self, c) -> None:                # t = new C
        tamano = self.tr.resumen.clases.get(c.arg1, 0)
        tamano = max(4, (tamano + 3) // 4 * 4)        # sbrk siempre alineado
        self.mips.emitir("li", "$a0", tamano, comentario=f"new {c.arg1}")
        self.mips.emitir("li", "$v0", 9)
        self.mips.emitir("syscall", comentario="sbrk (el heap viene en ceros)")
        destino = self.tr._destino(c.resultado)
        self.mips.emitir("move", destino, "$v0")
        self.tr.escribir(c.resultado, destino)

    def _campo(self, objeto, campo):
        clase = self.tr.tipo(objeto)
        info = self.atributos.get(clase, {}).get(campo)
        return clase, info

    def leer_campo(self, c) -> None:                  # t = o.campo
        objeto, campo = c.arg1, c.arg2
        clase, info = self._campo(objeto, campo)
        if info is None:
            self.tr.pendiente(c)
            return
        offset, tipo = info
        r_objeto = self.tr.registro_de(objeto, auxiliar="$a2")
        destino = self.tr._destino(c.resultado, [(objeto, r_objeto)], {r_objeto})
        if objeto != "this":
            self.antes_de_verificar()
            self.verificar_no_nulo(r_objeto, ERROR_OBJETO_NULL)
        self.mips.emitir("lbu" if es_byte(tipo) else "lw", destino,
                         f"{offset}({r_objeto})", comentario=f"{clase}.{campo}")
        self.tr.escribir(c.resultado, destino)

    def escribir_campo(self, c) -> None:              # o.campo = v
        campo, valor, objeto = c.arg1, str(c.arg2), c.resultado
        clase, info = self._campo(objeto, campo)
        if info is None:
            self.tr.pendiente(c)
            return
        offset, tipo = info
        r_valor = self._valor_para(valor, tipo, auxiliar="$a3")
        r_objeto = self.tr.registro_de(objeto, protegidos={r_valor}, auxiliar="$a2")
        if objeto != "this":
            self.antes_de_verificar()
            self.verificar_no_nulo(r_objeto, ERROR_OBJETO_NULL)
        self.mips.emitir("sb" if es_byte(tipo) else "sw", r_valor,
                         f"{offset}({r_objeto})", comentario=f"{clase}.{campo}")

    def _valor_para(self, valor, tipo_destino, auxiliar) -> str:
        """Registro con el valor; un integer guardado en un float se convierte."""
        if tipo_destino == FLOTANTE and self.tr.tipo(valor) == ENTERO:
            if tipo_literal(valor) == ENTERO:
                return self.tr.registro_de(str(float(valor)), auxiliar=auxiliar)
            r = self.tr.registro_de(valor, auxiliar=auxiliar)
            self.mips.emitir("mtc1", r, "$f4")
            self.mips.emitir("cvt.s.w", "$f4", "$f4", comentario="integer -> float")
            self.mips.emitir("mfc1", auxiliar, "$f4")
            return auxiliar
        return self.tr.registro_de(valor, auxiliar=auxiliar)

    def _receptor_para_obj(self, operando) -> tuple | None:
        marco = self.tr.marco
        if marco is None or not marco.es_metodo:
            return None
        tipo = self.tipo_obj(operando, self.tr.unidad.nombre)
        return marco.offset_receptor, tipo

    def leer_obj(self, operando, auxiliar, original) -> str:
        """Atributo sin `this` dentro de un método: obj+N es N(this)."""
        if not (isinstance(operando, str) and operando.startswith("obj+")):
            return original(operando, auxiliar)
        datos = self._receptor_para_obj(operando)
        if datos is None:
            return original(operando, auxiliar)
        offset_receptor, tipo = datos
        self.mips.emitir("lw", auxiliar, f"{offset_receptor}($fp)", comentario="this")
        self.mips.emitir("lbu" if es_byte(tipo) else "lw", auxiliar,
                         f"{_offset_obj(operando)}({auxiliar})", comentario=operando)
        return auxiliar

    def escribir_obj(self, destino, registro, original) -> None:
        if not (isinstance(destino, str) and destino.startswith("obj+")):
            original(destino, registro)
            return
        datos = self._receptor_para_obj(destino)
        if datos is None:
            original(destino, registro)
            return
        offset_receptor, tipo = datos
        self.mips.emitir("lw", "$a1", f"{offset_receptor}($fp)", comentario="this")
        self.mips.emitir("sb" if es_byte(tipo) else "sw", registro,
                         f"{_offset_obj(destino)}($a1)", comentario=destino)

    # ------------------------------------------------------------------
    # Cadenas
    # ------------------------------------------------------------------

    def _cadena_en(self, registro, operando) -> None:
        """Deja en `registro` ($a0 o $a1) un puntero a la cadena del operando,
        convirtiendo integer y boolean. Puede llamar a __int_a_cadena, que
        modifica $a0–$a3 y $v0."""
        tipo = self.tr.tipo(operando)
        if tipo == ENTERO:
            self.tr.cargar_en("$a0", operando)
            self.mips.emitir("jal", self.mips.usar_rutina(INT_A_CADENA, rutina_int_a_cadena))
            self.mips.emitir("move", registro, "$v0")
        elif tipo == BOOLEANO:
            if tipo_literal(operando) == BOOLEANO:
                self.mips.emitir("la", registro,
                                 "__verdadero" if operando == "true" else "__falso")
                return
            r = self.tr.registro_de(operando, auxiliar="$a3")
            self.mips.emitir("la", registro, "__verdadero")
            self.mips.emitir("la", "$a2", "__falso")
            self.mips.emitir("movz", registro, "$a2", r, comentario="false si es 0")
        elif tipo in (CADENA, NULO, None):
            self.tr.cargar_en(registro, operando)
        else:
            raise _NoSoportado(tipo)

    def concatenar(self, c) -> None:
        izquierda, derecha = c.arg1, c.arg2
        tipo_der = self.tr.tipo(derecha)
        try:
            self._cadena_en("$a0", izquierda)
            if tipo_der == ENTERO:
                # __int_a_cadena pisa $a0: se guarda la izquierda en la pila.
                self.mips.emitir("addiu", "$sp", "$sp", -4)
                self.mips.emitir("sw", "$a0", "0($sp)")
                self._cadena_en("$a1", derecha)
                self.mips.emitir("lw", "$a0", "0($sp)")
                self.mips.emitir("addiu", "$sp", "$sp", 4)
            else:
                self._cadena_en("$a1", derecha)
        except _NoSoportado:
            self.tr.pendiente(c)
            return
        self.mips.emitir("jal", self.mips.usar_rutina(CONCAT, rutina_concat))
        destino = self.tr._destino(c.resultado)
        self.mips.emitir("move", destino, "$v0")
        self.tr.escribir(c.resultado, destino)

    def comparar(self, c, original) -> None:
        """== / != entre cadenas compara contenido; lo demás, punteros/valores."""
        if not (self.tr.tipo(c.arg1) == CADENA and self.tr.tipo(c.arg2) == CADENA):
            original(c)
            return
        self.tr.cargar_en("$a0", c.arg1)
        self.tr.cargar_en("$a1", c.arg2)
        self.mips.emitir("jal", self.mips.usar_rutina(STRCMP, rutina_strcmp))
        destino = self.tr._destino(c.resultado)
        if c.op == T.IGUAL:
            self.mips.emitir("move", destino, "$v0")
        else:
            self.mips.emitir("xori", destino, "$v0", 1)
        self.tr.escribir(c.resultado, destino)

    # ------------------------------------------------------------------
    # Impresión de arreglos
    # ------------------------------------------------------------------

    def imprimir(self, operando, tipo, original) -> None:
        """Arreglos de integer, boolean o string (con cualquier número de
        dimensiones) se imprimen como el intérprete: [1, 2], [[1, 2], [3]]."""
        base, dimensiones = tipo or "", 0
        while base.endswith("[]"):
            base, dimensiones = base[:-2], dimensiones + 1
        if dimensiones == 0 or base not in _CLASE_ELEMENTO:
            original(operando, tipo)
            return
        self.tr.cargar_en("$a0", operando)
        self.mips.emitir("li", "$a1", _CLASE_ELEMENTO[base], comentario=f"elementos {base}")
        self.mips.emitir("li", "$a2", dimensiones, comentario="dimensiones")
        self.mips.emitir("jal", self.mips.usar_rutina(IMPRIMIR_ARREGLO, rutina_imprimir_arreglo))


class _NoSoportado(Exception):
    """Concatenación con un tipo que no se sabe convertir (float, objetos)."""


# ----------------------------------------------------------------------
# Rutinas de soporte. Solo modifican $a0-$a3 y $v0; lo demás se guarda en
# la pila. No tocan $v1 (pila de try/catch).
# ----------------------------------------------------------------------

def rutina_strlen(p) -> None:
    """$a0 = cadena -> $v0 = longitud. Usa $a3."""
    p.etiqueta(STRLEN)
    p.emitir("move", "$v0", "$a0")
    p.etiqueta("__Lstrlen_ciclo")
    p.emitir("lbu", "$a3", "0($v0)")
    p.emitir("beqz", "$a3", "__Lstrlen_fin")
    p.emitir("addiu", "$v0", "$v0", 1)
    p.emitir("j", "__Lstrlen_ciclo")
    p.etiqueta("__Lstrlen_fin")
    p.emitir("subu", "$v0", "$v0", "$a0")
    p.emitir("jr", "$ra")


def rutina_concat(p) -> None:
    """$a0 + $a1 -> $v0 (cadena nueva en el heap). Una cadena null se
    concatena como "null", igual que en el intérprete."""
    p.usar_rutina(STRLEN, rutina_strlen)
    p.etiqueta(CONCAT)
    p.emitir("addiu", "$sp", "$sp", -16)
    p.emitir("sw", "$ra", "0($sp)")
    p.emitir("sw", "$t0", "4($sp)")
    p.emitir("sw", "$t1", "8($sp)")
    p.emitir("sw", "$t2", "12($sp)")
    p.emitir("bnez", "$a0", "__Lconcat_a")
    p.emitir("la", "$a0", "__nulo")
    p.etiqueta("__Lconcat_a")
    p.emitir("bnez", "$a1", "__Lconcat_b")
    p.emitir("la", "$a1", "__nulo")
    p.etiqueta("__Lconcat_b")
    p.emitir("move", "$t0", "$a0")
    p.emitir("move", "$t1", "$a1")
    p.emitir("jal", STRLEN)
    p.emitir("move", "$t2", "$v0")
    p.emitir("move", "$a0", "$t1")
    p.emitir("jal", STRLEN)
    p.emitir("addu", "$a0", "$t2", "$v0")
    p.emitir("addiu", "$a0", "$a0", 4, comentario="+1 del 0 final, redondeado a 4")
    p.emitir("srl", "$a0", "$a0", 2)
    p.emitir("sll", "$a0", "$a0", 2)
    p.emitir("li", "$v0", 9)
    p.emitir("syscall", comentario="sbrk")
    p.emitir("move", "$t2", "$v0")
    p.etiqueta("__Lconcat_copiar_a")
    p.emitir("lbu", "$a2", "0($t0)")
    p.emitir("beqz", "$a2", "__Lconcat_copiar_b")
    p.emitir("sb", "$a2", "0($v0)")
    p.emitir("addiu", "$t0", "$t0", 1)
    p.emitir("addiu", "$v0", "$v0", 1)
    p.emitir("j", "__Lconcat_copiar_a")
    p.etiqueta("__Lconcat_copiar_b")
    p.emitir("lbu", "$a2", "0($t1)")
    p.emitir("sb", "$a2", "0($v0)", comentario="también copia el 0 final")
    p.emitir("beqz", "$a2", "__Lconcat_fin")
    p.emitir("addiu", "$t1", "$t1", 1)
    p.emitir("addiu", "$v0", "$v0", 1)
    p.emitir("j", "__Lconcat_copiar_b")
    p.etiqueta("__Lconcat_fin")
    p.emitir("move", "$v0", "$t2")
    p.emitir("lw", "$ra", "0($sp)")
    p.emitir("lw", "$t0", "4($sp)")
    p.emitir("lw", "$t1", "8($sp)")
    p.emitir("lw", "$t2", "12($sp)")
    p.emitir("addiu", "$sp", "$sp", 16)
    p.emitir("jr", "$ra")


def rutina_strcmp(p) -> None:
    """$a0 == $a1 por contenido -> $v0 = 1 / 0. Dos null son iguales; null y
    una cadena, distintos."""
    p.etiqueta(STRCMP)
    p.emitir("li", "$v0", 1)
    p.emitir("beq", "$a0", "$a1", "__Lstrcmp_fin", comentario="mismo puntero")
    p.emitir("li", "$v0", 0)
    p.emitir("beqz", "$a0", "__Lstrcmp_fin")
    p.emitir("beqz", "$a1", "__Lstrcmp_fin")
    p.etiqueta("__Lstrcmp_ciclo")
    p.emitir("lbu", "$a2", "0($a0)")
    p.emitir("lbu", "$a3", "0($a1)")
    p.emitir("bne", "$a2", "$a3", "__Lstrcmp_fin")
    p.emitir("addiu", "$a0", "$a0", 1)
    p.emitir("addiu", "$a1", "$a1", 1)
    p.emitir("bnez", "$a2", "__Lstrcmp_ciclo")
    p.emitir("li", "$v0", 1)
    p.etiqueta("__Lstrcmp_fin")
    p.emitir("jr", "$ra")


def rutina_int_a_cadena(p) -> None:
    """$a0 (integer) -> $v0 (cadena decimal en el heap). divu trata bien el
    -2147483648 porque su valor absoluto cabe sin signo."""
    p.etiqueta(INT_A_CADENA)
    p.emitir("move", "$a1", "$a0")
    p.emitir("li", "$a0", 12, comentario="signo + 10 dígitos + 0 final")
    p.emitir("li", "$v0", 9)
    p.emitir("syscall", comentario="sbrk")
    p.emitir("addiu", "$a2", "$v0", 11)
    p.emitir("sb", "$zero", "0($a2)")
    p.emitir("move", "$a3", "$a1", comentario="signo original")
    p.emitir("bgez", "$a1", "__Lint_cadena_ciclo")
    p.emitir("subu", "$a1", "$zero", "$a1")
    p.etiqueta("__Lint_cadena_ciclo")
    p.emitir("li", "$a0", 10)
    p.emitir("divu", "$a1", "$a0")
    p.emitir("mfhi", "$a0")
    p.emitir("addiu", "$a0", "$a0", 48, comentario="'0' + dígito")
    p.emitir("addiu", "$a2", "$a2", -1)
    p.emitir("sb", "$a0", "0($a2)")
    p.emitir("mflo", "$a1")
    p.emitir("bnez", "$a1", "__Lint_cadena_ciclo")
    p.emitir("bgez", "$a3", "__Lint_cadena_fin")
    p.emitir("li", "$a0", 45, comentario="'-'")
    p.emitir("addiu", "$a2", "$a2", -1)
    p.emitir("sb", "$a0", "0($a2)")
    p.etiqueta("__Lint_cadena_fin")
    p.emitir("move", "$v0", "$a2")
    p.emitir("jr", "$ra")


def rutina_imprimir_arreglo(p) -> None:
    """$a0 = arreglo, $a1 = tipo de elemento (0 integer, 1 boolean, 2 string),
    $a2 = dimensiones. Imprime [e0, e1, ...] sin salto de línea; es recursiva
    para las matrices. Guarda $t0-$t3 y $ra en la pila."""
    p.etiqueta(IMPRIMIR_ARREGLO)
    p.emitir("addiu", "$sp", "$sp", -24)
    p.emitir("sw", "$ra", "0($sp)")
    p.emitir("sw", "$t0", "4($sp)")
    p.emitir("sw", "$t1", "8($sp)")
    p.emitir("sw", "$t2", "12($sp)")
    p.emitir("sw", "$t3", "16($sp)")
    p.emitir("sw", "$a1", "20($sp)")
    p.emitir("move", "$t0", "$a0", comentario="arreglo")
    p.emitir("move", "$t3", "$a2", comentario="dimensiones")
    p.emitir("bnez", "$t0", "__Limp_arr_no_nulo")
    p.emitir("la", "$a0", "__nulo")
    p.emitir("li", "$v0", 4)
    p.emitir("syscall")
    p.emitir("j", "__Limp_arr_fin")
    p.etiqueta("__Limp_arr_no_nulo")
    p.emitir("li", "$a0", 91, comentario="'['")
    p.emitir("li", "$v0", 11)
    p.emitir("syscall")
    p.emitir("lw", "$t1", "0($t0)", comentario="longitud")
    p.emitir("li", "$t2", 0, comentario="i")
    p.etiqueta("__Limp_arr_ciclo")
    p.emitir("beq", "$t2", "$t1", "__Limp_arr_cierre")
    p.emitir("beqz", "$t2", "__Limp_arr_elemento")
    p.emitir("la", "$a0", "__separador")
    p.emitir("li", "$v0", 4)
    p.emitir("syscall")
    p.etiqueta("__Limp_arr_elemento")
    p.emitir("sll", "$a0", "$t2", 2)
    p.emitir("addu", "$a0", "$a0", "$t0")
    p.emitir("lw", "$a0", "4($a0)")
    p.emitir("lw", "$a1", "20($sp)")
    p.emitir("li", "$a2", 1)
    p.emitir("beq", "$t3", "$a2", "__Limp_arr_simple")
    p.emitir("addiu", "$a2", "$t3", -1)
    p.emitir("jal", IMPRIMIR_ARREGLO)
    p.emitir("j", "__Limp_arr_siguiente")
    p.etiqueta("__Limp_arr_simple")
    p.emitir("li", "$v0", 1)
    p.emitir("beqz", "$a1", "__Limp_arr_syscall", comentario="integer")
    p.emitir("li", "$v0", 4)
    p.emitir("li", "$a2", 2)
    p.emitir("beq", "$a1", "$a2", "__Limp_arr_cadena")
    p.emitir("la", "$a1", "__falso", comentario="boolean")
    p.emitir("move", "$a2", "$a0")
    p.emitir("la", "$a0", "__verdadero")
    p.emitir("movz", "$a0", "$a1", "$a2")
    p.emitir("j", "__Limp_arr_syscall")
    p.etiqueta("__Limp_arr_cadena")
    p.emitir("bnez", "$a0", "__Limp_arr_syscall")
    p.emitir("la", "$a0", "__nulo")
    p.etiqueta("__Limp_arr_syscall")
    p.emitir("syscall")
    p.etiqueta("__Limp_arr_siguiente")
    p.emitir("addiu", "$t2", "$t2", 1)
    p.emitir("j", "__Limp_arr_ciclo")
    p.etiqueta("__Limp_arr_cierre")
    p.emitir("li", "$a0", 93, comentario="']'")
    p.emitir("li", "$v0", 11)
    p.emitir("syscall")
    p.etiqueta("__Limp_arr_fin")
    p.emitir("lw", "$ra", "0($sp)")
    p.emitir("lw", "$t0", "4($sp)")
    p.emitir("lw", "$t1", "8($sp)")
    p.emitir("lw", "$t2", "12($sp)")
    p.emitir("lw", "$t3", "16($sp)")
    p.emitir("addiu", "$sp", "$sp", 24)
    p.emitir("jr", "$ra")


def _error_objeto_null(p) -> None:
    p.etiqueta(ERROR_OBJETO_NULL)
    p.emitir("la", "$a0", "__msg_error_objeto_null")
    p.emitir("jal", "__lanzar")


# ----------------------------------------------------------------------
# Registro
# ----------------------------------------------------------------------

def registrar(traductor) -> None:
    datos = Datos(traductor)
    traductor.datos = datos
    datos.envolver_tipos()

    traductor.manejadores[T.NUEVO_ARREGLO] = datos.nuevo_arreglo
    traductor.manejadores[T.LEER_INDICE] = datos.leer_indice
    traductor.manejadores[T.ESCRIBIR_INDICE] = datos.escribir_indice
    traductor.manejadores[T.LONGITUD] = datos.longitud
    traductor.manejadores[T.NUEVO] = datos.nuevo_objeto
    traductor.manejadores[T.LEER_CAMPO] = datos.leer_campo
    traductor.manejadores[T.ESCRIBIR_CAMPO] = datos.escribir_campo

    for op in (T.IGUAL, T.DISTINTO):
        original = traductor.manejadores[op]
        traductor.manejadores[op] = lambda c, o=original: datos.comparar(c, o)

    leer_original = traductor.operando_especial
    escribir_original = traductor.asignar_especial
    imprimir_original = traductor.imprimir_especial
    traductor.operando_especial = (
        lambda op, aux: datos.leer_obj(op, aux, leer_original))
    traductor.asignar_especial = (
        lambda destino, reg: datos.escribir_obj(destino, reg, escribir_original))
    traductor.imprimir_especial = (
        lambda op, tipo: datos.imprimir(op, tipo, imprimir_original))
    traductor.concatenar = datos.concatenar

    traductor.mips.usar_rutina(ERROR_OBJETO_NULL, _error_objeto_null)
    traductor.mips.datos_extra.append('__nulo: .asciiz "null"')
    traductor.mips.datos_extra.append('__separador: .asciiz ", "')
    traductor.mips.datos_extra.append(
        '__msg_error_objeto_null: .asciiz "acceso a un objeto null"')
