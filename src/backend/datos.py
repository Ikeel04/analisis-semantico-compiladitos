"""
Manejadores de datos compuestos (parte 3): arreglos.

`registrar(traductor)` agrega a `traductor.manejadores` los cuádruplos de
arreglos.

Memoria (heap con `sbrk`, que MARS entrega en ceros):

    arreglo:  [longitud][e0][e1]...      palabras de 4 bytes; el puntero
                                         apunta a la longitud

| TAC               | MIPS                                                    |
|-------------------|---------------------------------------------------------|
| `t = newarray n`  | `sbrk 4·(n+1)`, `sw n, 0(t)`                            |
| `t = a[i]`        | null → `__error_null`; `0 ≤ i < len` → `__error_indice`; `lw t, 4+4i(a)` |
| `a[i] = v`        | mismas verificaciones; `sw v, 4+4i(a)`                  |
| `t = length a`    | `lw t, 0(a)`                                            |

Registros: los operandos los pone el asignador (o `$a2`/`$a3`/`$a0` si son
literales); para direcciones intermedias se usa solo `$a1`. `$v1` NO se toca.
"""

from __future__ import annotations

import tac as T
from memoria import alinear, tamano_de
from tipos import BOOLEANO, CADENA, ENTERO, FLOTANTE, NULO, es_byte, tipo_literal
from unidades import definicion, es_direccion, es_nombre




class Datos:
    """Estado y manejadores de la parte 3 (uno por traductor)."""

    def __init__(self, traductor):
        self.tr = traductor

    @property
    def mips(self):
        return self.tr.mips

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

# ----------------------------------------------------------------------
# Registro
# ----------------------------------------------------------------------

def registrar(traductor) -> None:
    datos = Datos(traductor)
    traductor.datos = datos

    traductor.manejadores[T.NUEVO_ARREGLO] = datos.nuevo_arreglo
    traductor.manejadores[T.LEER_INDICE] = datos.leer_indice
    traductor.manejadores[T.ESCRIBIR_INDICE] = datos.escribir_indice
    traductor.manejadores[T.LONGITUD] = datos.longitud
