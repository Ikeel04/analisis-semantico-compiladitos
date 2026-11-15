"""
Traducción de TAC a ensamblador MIPS32.

TraductorMIPS recorre cada unidad (main y cada función), parte en bloques
básicos, calcula la vida de los nombres y despacha cada cuádruplo a un
manejador. Los manejadores piden registros al AsignadorRegistros; las
fronteras de bloque y de llamada (guardar lo sucio, olvidar los registros) se
resuelven aquí, de forma genérica, para que los manejadores de las partes 2 y
3 solo tengan que emitir sus instrucciones.

Operaciones sin manejador: se emiten como `# [pendiente] <cuádruplo>` y se
listan en `pendientes`. Ver docs/DISENO_MIPS.md §6.
"""

from __future__ import annotations

import os
import struct
import sys

_SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_INTERMEDIO = os.path.join(_SRC, "intermediate")
if _INTERMEDIO not in sys.path:
    sys.path.insert(0, _INTERMEDIO)

import tac as T
from extensiones import aplicar as aplicar_extensiones
from marcos import construir_marco, emitir_epilogo, emitir_prologo, es_metodo
from programa_mips import ProgramaMIPS, etiqueta_fin, etiqueta_funcion
from registros import AsignadorRegistros
from tipos import (
    ARITMETICAS,
    BOOLEANO,
    CADENA,
    ENTERO,
    FLOTANTE,
    LOGICAS,
    NULO,
    RELACIONALES,
    InferenciaTipos,
    es_byte,
    tipo_literal,
)
from unidades import (
    TERMINAN_BLOQUE,
    definicion,
    es_direccion,
    es_nombre,
    es_temporal,
    indice_temporal,
    separar_unidades,
    usos,
)
from vida import InfoVida

TAMANO_PALABRA_TEMPORAL = 8

INSTRUCCION_ENTERA = {
    T.SUMA: "addu", T.RESTA: "subu", T.MULTIPLICACION: "mul",
    T.MENOR: "slt", T.MENOR_IGUAL: "sle", T.MAYOR: "sgt", T.MAYOR_IGUAL: "sge",
    T.IGUAL: "seq", T.DISTINTO: "sne",
    T.Y_LOGICO: "and", T.O_LOGICO: "or",
}
INSTRUCCION_FLOTANTE = {
    T.SUMA: "add.s", T.RESTA: "sub.s", T.MULTIPLICACION: "mul.s", T.DIVISION: "div.s",
}
# (comparación, intercambiar operandos, resultado si la bandera está apagada)
COMPARACION_FLOTANTE = {
    T.IGUAL: ("c.eq.s", False, "movf"), T.DISTINTO: ("c.eq.s", False, "movt"),
    T.MENOR: ("c.lt.s", False, "movf"), T.MENOR_IGUAL: ("c.le.s", False, "movf"),
    T.MAYOR: ("c.lt.s", True, "movf"), T.MAYOR_IGUAL: ("c.le.s", True, "movf"),
}


def bits_flotante(valor) -> str:
    """Patrón IEEE-754 de precisión simple, para cargarlo con `li`."""
    return "0x%08X" % struct.unpack(">I", struct.pack(">f", float(valor)))[0]


def _alinear_8(valor: int) -> int:
    return valor if valor % 8 == 0 else valor + 8 - valor % 8


def es_funcion_anidada(nombre_cualificado: str, clases) -> bool:
    """'contador.interno' es una función anidada (closure): su prefijo es el
    nombre de la función que la declara, no el de una clase. 'Animal.hablar' es
    un método (prefijo = clase). Las funciones de primer nivel no son."""
    if "." not in nombre_cualificado:
        return False
    return nombre_cualificado.rsplit(".", 1)[0] not in clases


class TraductorMIPS:
    def __init__(self, programa_tac, tabla, resumen):
        self.tac = programa_tac
        self.resumen = resumen
        self.tipos = InferenciaTipos(tabla, resumen)
        self.mips = ProgramaMIPS()
        self.unidades = separar_unidades(programa_tac)
        self.marcos: dict = {}
        self.traza: list[dict] = []
        self.pendientes: list[str] = []
        self.estadisticas_registros: dict[str, dict] = {}
        self._args: list[str] = []   # operandos apilados por `parametro`, para `llamar`

        self.base_temporales_globales = _alinear_8(resumen.tamano_global)

        self.manejadores = {
            T.ASIGNAR: self.asignar,
            T.NEGATIVO: self.unaria,
            T.NEGACION: self.unaria,
            T.PRINT: self.imprimir,
            T.PARAMETRO: self.parametro,
            T.LLAMAR: self.llamar,
            T.RETORNAR: self.retornar,
            T.COMENTARIO: self.comentario,
        }
        for op in ARITMETICAS | RELACIONALES | LOGICAS:
            self.manejadores[op] = self.binaria
        # Partes 2 y 3: agregan manejadores y reemplazan los puntos de extensión.
        aplicar_extensiones(self)

        # Estado de la unidad en curso.
        self.unidad = None
        self.marco = None
        self.vida = None
        self.asignador = None
        self.pos = 0
        self.tipos_temporales: dict = {}

    # ------------------------------------------------------------------
    # Recorrido
    # ------------------------------------------------------------------

    def traducir(self) -> ProgramaMIPS:
        principal = self.unidades[0]
        self.mips.tamano_globales = (self.base_temporales_globales
                                     + TAMANO_PALABRA_TEMPORAL * principal.max_temporal())
        self.mips.etiqueta("main")
        self.mips.emitir("la", "$s7", "__globales", comentario="base del área global")
        self.mips.emitir("move", "$fp", "$sp")
        self._traducir_unidad(principal, None)
        self.mips.emitir("li", "$v0", 10, comentario="fin del programa")
        self.mips.emitir("syscall")

        for unidad in self.unidades[1:]:
            marco = construir_marco(
                unidad.nombre,
                self.resumen.registros.get(unidad.nombre),
                unidad.max_temporal(),
                es_metodo(unidad.nombre, self.tipos.clases),
                anidada=es_funcion_anidada(unidad.nombre, self.tipos.clases),
            )
            self.marcos[unidad.nombre] = marco
            self.mips.comentario(f"function {unidad.nombre}")
            emitir_prologo(self.mips, marco)
            self._traducir_unidad(unidad, marco)
            emitir_epilogo(self.mips, marco)
        self.mips.emitir_rutinas()
        return self.mips

    def _traducir_unidad(self, unidad, marco) -> None:
        self.unidad = unidad
        self.marco = marco
        self.vida = InfoVida(unidad)
        self.tipos_temporales = {}
        self.asignador = AsignadorRegistros(self.mips, self._ubicacion)

        anterior = None
        for pos, (indice, c) in enumerate(unidad.instrucciones):
            self.pos = pos
            inicio = len(self.mips.texto)

            if pos > 0 and self.vida.es_inicio_de_bloque(pos):
                if anterior.op not in TERMINAN_BLOQUE:
                    self._guardar_fin_de_bloque(pos - 1)
                self.asignador.invalidar()
            if c.op in TERMINAN_BLOQUE:
                if c.op == T.RETORNAR:
                    self.asignador.guardar_sucios(self._es_global, "antes de return")
                else:
                    self._guardar_fin_de_bloque(pos)

            tipo_resultado = self.tipos.tipo_resultado(c, unidad.nombre,
                                                       self.tipos_temporales)
            self.manejadores.get(c.op, self.pendiente)(c)
            if es_temporal(definicion(c)):
                self.tipos_temporales[c.resultado] = tipo_resultado
            self._liberar_muertos(c, pos)

            self.traza.append({
                "Unidad": unidad.nombre,
                "#": indice,
                "TAC": str(c),
                "MIPS": "\n".join(str(i).strip() for i in self.mips.texto[inicio:]),
                "Descriptor de registros": self.asignador.instantanea(),
            })
            anterior = c

        if anterior is not None and anterior.op not in TERMINAN_BLOQUE and marco:
            self.asignador.guardar_sucios(self._es_global, "fin de función")

        estadisticas = dict(self.asignador.estadisticas)
        estadisticas["registros usados"] = len(self.asignador.usados)
        self.estadisticas_registros[unidad.nombre] = estadisticas

    def _guardar_fin_de_bloque(self, pos) -> None:
        vivos = self.vida.vivos_al_salir(pos)
        self.asignador.guardar_sucios(lambda n: es_direccion(n) or n in vivos)

    def _liberar_muertos(self, c, pos) -> None:
        for nombre in usos(c) + [definicion(c)]:
            if es_temporal(nombre) and not self.vida.vivo_despues(nombre, pos):
                self.asignador.olvidar(nombre)

    @staticmethod
    def _es_global(nombre) -> bool:
        return nombre.startswith("global+")

    # ------------------------------------------------------------------
    # Ubicaciones y operandos
    # ------------------------------------------------------------------

    def _ubicacion(self, nombre) -> tuple[str, bool]:
        """Dirección de memoria de un nombre y si se accede por byte."""
        if es_temporal(nombre):
            k = indice_temporal(nombre)
            if self.marco is None:
                offset = self.base_temporales_globales + TAMANO_PALABRA_TEMPORAL * (k - 1)
                return f"{offset}($s7)", False
            return f"{self.marco.offset_temporal(k)}($fp)", False
        base, offset = nombre.split("+")
        registro_base = "$s7" if base == "global" else "$fp"
        return f"{offset}({registro_base})", es_byte(self.tipo(nombre))

    def tipo(self, operando):
        return self.tipos.tipo_de(operando, self.unidad.nombre, self.tipos_temporales)

    def _vivo(self, nombre, pos) -> bool:
        return self.vida.vivo_despues(nombre, pos)

    def cargar_literal(self, registro, operando) -> bool:
        """Carga un literal en `registro`. Devuelve False si no es literal."""
        tipo = tipo_literal(operando)
        if tipo == ENTERO:
            self.mips.emitir("li", registro, operando)
        elif tipo == BOOLEANO:
            self.mips.emitir("li", registro, 1 if operando == "true" else 0)
        elif tipo == NULO:
            self.mips.emitir("li", registro, 0)
        elif tipo == FLOTANTE:
            self.mips.emitir("li", registro, bits_flotante(operando),
                             comentario=f"float {operando}")
        elif tipo == CADENA:
            self.mips.emitir("la", registro, self.mips.cadena(operando))
        else:
            return False
        return True

    def registro_de(self, operando, protegidos=(), auxiliar="$a2") -> str:
        """Registro con el valor del operando: uno asignado para nombres, `$zero`
        para el cero y un auxiliar para el resto de literales."""
        if es_nombre(operando):
            return self.asignador.leer(operando, self.pos, self._vivo, protegidos)
        if operando in ("0", "false", "null"):
            return "$zero"
        if self.cargar_literal(auxiliar, operando):
            return auxiliar
        if operando == "this" and self.marco is not None and self.marco.es_metodo:
            self.mips.emitir("lw", auxiliar, f"{self.marco.offset_receptor}($fp)",
                             comentario="this")
            return auxiliar
        return self.operando_especial(operando, auxiliar)

    def cargar_en(self, registro_fijo, operando) -> None:
        """Deja el operando en un registro fijo ($v0, $a0)."""
        if not self.cargar_literal(registro_fijo, operando):
            self.mips.emitir("move", registro_fijo, self.registro_de(operando))

    def resultado_en(self, destino, operandos=(), protegidos=()) -> str:
        return self.asignador.para_resultado(destino, list(operandos), self.pos,
                                             self._vivo, set(protegidos))

    def escribir(self, destino, registro) -> None:
        if es_nombre(destino):
            self.asignador.escribir(destino, registro)
        else:
            self.asignar_especial(destino, registro)

    def _destino(self, destino, operandos=(), protegidos=()) -> str:
        """Registro para el resultado; si el destino no es un nombre asignable
        (atributo, variable capturada) se calcula en un auxiliar."""
        if es_nombre(destino):
            return self.resultado_en(destino, operandos, protegidos)
        return "$a3"

    # ------------------------------------------------------------------
    # Puntos de extensión (partes 2 y 3)
    # ------------------------------------------------------------------

    def pendiente(self, c) -> None:
        self.mips.comentario(f"[pendiente] {c}")
        self.pendientes.append(f"{self.unidad.nombre}: {c}")

    def operando_especial(self, operando, auxiliar) -> str:
        """Operandos que no son literales ni direcciones: variables capturadas
        (parte 2) y atributos obj+N (parte 3)."""
        if self._es_capturada(operando):
            return self._leer_capturada(operando, auxiliar)
        self.mips.comentario(f"[pendiente] leer {operando}")
        self.pendientes.append(f"{self.unidad.nombre}: leer {operando}")
        return "$zero"

    def asignar_especial(self, destino, registro) -> None:
        if self._es_capturada(destino):
            simbolo = self._simbolo_capturado(destino)
            marco = self.marco
            if (simbolo is None or not simbolo.direccion or marco is None
                    or marco.offset_enlace_acceso is None):
                self.mips.comentario(f"[pendiente] escribir {destino}")
                self.pendientes.append(f"{self.unidad.nombre}: escribir {destino}")
                return
            offset = int(str(simbolo.direccion).split("+")[1])
            self.mips.emitir("lw", "$v1", f"{marco.offset_enlace_acceso}($fp)",
                            comentario="enlace de acceso")
            self.mips.emitir("sb" if es_byte(simbolo.type) else "sw", registro, f"{offset}($v1)")
            return
        self.mips.comentario(f"[pendiente] escribir {destino}")
        self.pendientes.append(f"{self.unidad.nombre}: escribir {destino}")

    def _convertir_argumentos_flotantes(self, nombre: str, cantidad: int) -> None:
        """Si un parámetro declarado float recibe un argumento integer, el TAC no
        convierte (`param` apila los bits tal cual): se convierte aquí, en el
        sitio de la llamada, antes del `jal`. El intérprete hace lo mismo."""
        if not cantidad:
            self._args.clear()
            return
        args = self._args[-cantidad:]
        self._args = self._args[:-cantidad]
        registro = self.resumen.registros.get(nombre)
        if registro is None:
            return
        for i, param in enumerate(registro.parametros):
            if i >= len(args):
                break
            if param.type == FLOTANTE and self.tipo(args[i]) == ENTERO:
                offset = 4 * (cantidad - 1 - i)
                self.mips.emitir("lw", "$a2", f"{offset}($sp)",
                                 comentario="entero -> flotante")
                self.mips.emitir("mtc1", "$a2", "$f4")
                self.mips.emitir("cvt.s.w", "$f4", "$f4")
                self.mips.emitir("mfc1", "$a2", "$f4")
                self.mips.emitir("sw", "$a2", f"{offset}($sp)")

    # ------------------------------------------------------------------
    # Variables capturadas (funciones anidadas / closures, parte 2)
    # ------------------------------------------------------------------

    def _enunciada(self) -> str:
        """Función que contiene al scope en el que se lee/escribe (sin el
        sufijo de la anidada): 'contador.interno' -> 'contador'."""
        nombre = self.unidad.nombre or ""
        return nombre.rsplit(".", 1)[0] if "." in nombre else nombre

    def _simbolo_capturado(self, nombre):
        """Símbolo de la variable capturada: vive en el marco de la función que
        la declara, a través del enlace de acceso."""
        registro = self.resumen.registros.get(self._enunciada())
        if registro is None:
            return None
        for simbolo in list(registro.parametros) + list(registro.locales):
            if simbolo.name == nombre:
                return simbolo
        return None

    def _es_capturada(self, nombre) -> bool:
        return (self.marco is not None and self.marco.es_funcion_anidada
                and isinstance(nombre, str) and "." not in nombre)

    def _enlace_de_acceso(self):
        """$v1 con el frame pointer de la función que captura (enlace recibido)."""
        marco = self.marco
        if marco is None or marco.offset_enlace_acceso is None:
            return None
        self.mips.emitir("lw", "$v1", f"{marco.offset_enlace_acceso}($fp)",
                        comentario="enlace de acceso")
        return "$v1"

    def _leer_capturada(self, nombre, auxiliar) -> str:
        simbolo = self._simbolo_capturado(nombre)
        marco = self.marco
        if (simbolo is None or not simbolo.direccion or marco is None
                or marco.offset_enlace_acceso is None):
            self.mips.comentario(f"[pendiente] leer {nombre}")
            self.pendientes.append(f"{self.unidad.nombre}: leer capturada {nombre}")
            return "$zero"
        offset = int(str(simbolo.direccion).split("+")[1])
        enlace = self._enlace_de_acceso()
        self.mips.emitir("lbu" if es_byte(simbolo.type) else "lw", auxiliar,
                         f"{offset}({enlace})")
        return auxiliar

    def antes_de_dividir(self, divisor) -> None:
        """Parte 2: verificar división por cero y saltar al catch."""

    def concatenar(self, c) -> None:
        """Parte 3: concatenación de cadenas en tiempo de ejecución."""
        self.pendiente(c)

    def imprimir_especial(self, operando, tipo) -> None:
        """Parte 3: impresión de arreglos y objetos."""
        self.mips.emitir("move", "$a0", self.registro_de(operando))
        self.mips.emitir("li", "$v0", 1)
        self.mips.emitir("syscall")

    # ------------------------------------------------------------------
    # Manejadores de la parte 1
    # ------------------------------------------------------------------

    def comentario(self, c) -> None:
        self.mips.comentario(c.arg1)

    def asignar(self, c) -> None:
        destino, fuente = c.resultado, c.arg1
        if self.tipo(destino) == FLOTANTE and self.tipo(fuente) == ENTERO:
            if tipo_literal(fuente) == ENTERO:
                registro = self._destino(destino)
                self.cargar_literal(registro, str(float(fuente)))
            else:
                origen = self.registro_de(fuente)
                registro = self._destino(destino, [(fuente, origen)], {origen})
                self.mips.emitir("mtc1", origen, "$f4")
                self.mips.emitir("cvt.s.w", "$f4", "$f4", comentario="integer -> float")
                self.mips.emitir("mfc1", registro, "$f4")
            self.escribir(destino, registro)
            return

        if es_nombre(fuente) and es_nombre(destino):
            self.asignador.copiar(destino, self.registro_de(fuente))
            return
        if es_nombre(fuente):
            self.escribir(destino, self.registro_de(fuente))
            return
        registro = self._destino(destino)
        if not self.cargar_literal(registro, fuente):
            self.mips.emitir("move", registro, self.registro_de(fuente, auxiliar="$a2"))
        self.escribir(destino, registro)

    def binaria(self, c) -> None:
        op, izquierda, derecha, destino = c.op, c.arg1, c.arg2, c.resultado
        tipo_izq, tipo_der = self.tipo(izquierda), self.tipo(derecha)
        if op == T.SUMA and CADENA in (tipo_izq, tipo_der):
            self.concatenar(c)
            return
        if FLOTANTE in (tipo_izq, tipo_der) and op not in LOGICAS and op != T.MODULO:
            self._binaria_flotante(c, tipo_izq, tipo_der)
            return

        # Inmediatos: x = 5 + y se trata como y + 5 (suma y producto conmutan).
        if (op in (T.SUMA, T.MULTIPLICACION) and tipo_literal(izquierda) == ENTERO
                and tipo_literal(derecha) != ENTERO):
            izquierda, derecha = derecha, izquierda

        r_izq = self.registro_de(izquierda, auxiliar="$a2")
        inmediato = self._inmediato(op, derecha)
        if inmediato is not None:
            registro = self._destino(destino, [(izquierda, r_izq)], {r_izq})
            instruccion, valor = inmediato
            self.mips.emitir(instruccion, registro, r_izq, valor)
            self.escribir(destino, registro)
            return

        r_der = self.registro_de(derecha, protegidos={r_izq}, auxiliar="$a3")
        registro = self._destino(destino, [(izquierda, r_izq), (derecha, r_der)],
                                 {r_izq, r_der})
        if op in (T.DIVISION, T.MODULO):
            self.antes_de_dividir(r_der)
            self.mips.emitir("div", r_izq, r_der)
            self.mips.emitir("mflo" if op == T.DIVISION else "mfhi", registro)
        else:
            self.mips.emitir(INSTRUCCION_ENTERA[op], registro, r_izq, r_der)
        self.escribir(destino, registro)

    @staticmethod
    def _inmediato(op, operando):
        """(instrucción, valor) si el operando derecho cabe como inmediato."""
        if tipo_literal(operando) != ENTERO:
            return None
        valor = int(operando)
        if op == T.SUMA and -32768 <= valor <= 32767:
            return "addiu", valor
        if op == T.RESTA and -32767 <= valor <= 32768:
            return "addiu", -valor
        if op == T.MULTIPLICACION:
            return "mul", valor
        return None

    def _a_flotante(self, operando, tipo, registro_fp, protegidos) -> str:
        if tipo_literal(operando) == ENTERO:
            operando, tipo = str(float(operando)), FLOTANTE
        r = self.registro_de(operando, protegidos=protegidos,
                             auxiliar="$a2" if registro_fp == "$f4" else "$a3")
        self.mips.emitir("mtc1", r, registro_fp)
        if tipo != FLOTANTE:
            self.mips.emitir("cvt.s.w", registro_fp, registro_fp)
        return r

    def _binaria_flotante(self, c, tipo_izq, tipo_der) -> None:
        op, destino = c.op, c.resultado
        r_izq = self._a_flotante(c.arg1, tipo_izq, "$f4", ())
        r_der = self._a_flotante(c.arg2, tipo_der, "$f6", {r_izq})
        registro = self._destino(destino, [(c.arg1, r_izq), (c.arg2, r_der)],
                                 {r_izq, r_der})
        if op in INSTRUCCION_FLOTANTE:
            self.mips.emitir(INSTRUCCION_FLOTANTE[op], "$f4", "$f4", "$f6")
            self.mips.emitir("mfc1", registro, "$f4")
        else:
            comparacion, intercambiar, mover = COMPARACION_FLOTANTE[op]
            a, b = ("$f6", "$f4") if intercambiar else ("$f4", "$f6")
            self.mips.emitir(comparacion, a, b)
            self.mips.emitir("li", registro, 1)
            self.mips.emitir(mover, registro, "$zero")
        self.escribir(destino, registro)

    def unaria(self, c) -> None:
        destino, operando = c.resultado, c.arg1
        if c.op == T.NEGATIVO and tipo_literal(operando) in (ENTERO, FLOTANTE):
            registro = self._destino(destino)
            self.cargar_literal(registro, operando[1:] if operando.startswith("-")
                                else "-" + operando)
            self.escribir(destino, registro)
            return
        r = self.registro_de(operando)
        registro = self._destino(destino, [(operando, r)], {r})
        if c.op == T.NEGACION:
            self.mips.emitir("xori", registro, r, 1)
        elif self.tipo(operando) == FLOTANTE:
            self.mips.emitir("mtc1", r, "$f4")
            self.mips.emitir("neg.s", "$f4", "$f4")
            self.mips.emitir("mfc1", registro, "$f4")
        else:
            self.mips.emitir("subu", registro, "$zero", r)
        self.escribir(destino, registro)

    def imprimir(self, c) -> None:
        operando = c.arg1
        tipo = self.tipo(operando)
        if tipo == CADENA:
            self.cargar_en("$a0", operando)
            self.mips.emitir("li", "$v0", 4)
            self.mips.emitir("syscall")
        elif tipo == FLOTANTE:
            r = self.registro_de(operando)
            self.mips.emitir("mtc1", r, "$f12")
            self.mips.emitir("li", "$v0", 2)
            self.mips.emitir("syscall")
        elif tipo == BOOLEANO:
            r = self.registro_de(operando)
            self.mips.emitir("la", "$a0", "__verdadero")
            self.mips.emitir("la", "$a1", "__falso")
            self.mips.emitir("movz", "$a0", "$a1", r, comentario="false si es 0")
            self.mips.emitir("li", "$v0", 4)
            self.mips.emitir("syscall")
        elif tipo in (ENTERO, None, NULO):
            self.cargar_en("$a0", operando)
            self.mips.emitir("li", "$v0", 1)
            self.mips.emitir("syscall")
        else:
            self.imprimir_especial(operando, tipo)
        self.mips.emitir("li", "$a0", 10, comentario="salto de línea")
        self.mips.emitir("li", "$v0", 11)
        self.mips.emitir("syscall")

    def parametro(self, c) -> None:
        r = self.registro_de(c.arg1)
        self._args.append(c.arg1)
        self.mips.emitir("addiu", "$sp", "$sp", -4)
        self.mips.emitir("sw", r, "0($sp)", comentario=f"param {c.arg1}")

    def llamar(self, c) -> None:
        nombre, cantidad, destino = c.arg1, int(c.arg2), c.resultado
        pos = self.pos
        self._convertir_argumentos_flotantes(nombre, cantidad)
        self.asignador.guardar_sucios(lambda n: self._vivo(n, pos), "antes de call")
        if es_funcion_anidada(nombre, self.tipos.clases):
            # Función anidada (closure): el llamador pasa su enlace de acceso en
            # $v1 antes del jal; el prólogo de la anidada lo guarda en su celda.
            if self.marco is not None and self.marco.es_funcion_anidada:
                self.mips.emitir("lw", "$v1", f"{self.marco.offset_enlace_acceso}($fp)",
                                comentario="enlace de acceso")
            else:
                self.mips.emitir("move", "$v1", "$fp", comentario="enlace de acceso")
        self.mips.emitir("jal", etiqueta_funcion(nombre))
        if cantidad:
            self.mips.emitir("addiu", "$sp", "$sp", 4 * cantidad,
                             comentario="desapilar argumentos")
        # El llamado usa los mismos registros: lo que había ya no vale.
        self.asignador.invalidar()
        if destino is not None:
            registro = self._destino(destino)
            self.mips.emitir("move", registro, "$v0")
            self.escribir(destino, registro)

    def retornar(self, c) -> None:
        if c.arg1 is not None:
            self.cargar_en("$v0", c.arg1)
        self.mips.emitir("j", etiqueta_fin(self.unidad.nombre))
