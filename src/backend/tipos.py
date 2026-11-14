"""
Tipo de cada operando del TAC.

El TAC no lleva tipos, pero el ensamblador los necesita: un boolean se guarda
con `sb`, un float se suma con `add.s` y cada tipo se imprime con otra llamada
al sistema. Las direcciones toman el tipo de la tabla de símbolos; los
temporales, del cuádruplo que los definió (el traductor los va anotando).
"""

from __future__ import annotations

import os
import re
import sys

_SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_INTERMEDIO = os.path.join(_SRC, "intermediate")
if _INTERMEDIO not in sys.path:
    sys.path.insert(0, _INTERMEDIO)

import tac as T
from memoria import tamano_de

ENTERO = "integer"
FLOTANTE = "float"
BOOLEANO = "boolean"
CADENA = "string"
NULO = "null"

_ENTERO = re.compile(r"^-?\d+$")
_FLOTANTE = re.compile(r"^-?(\d+\.\d*|\.\d+)([eE][-+]?\d+)?$")

RELACIONALES = {T.IGUAL, T.DISTINTO, T.MENOR, T.MENOR_IGUAL, T.MAYOR, T.MAYOR_IGUAL}
LOGICAS = {T.Y_LOGICO, T.O_LOGICO}
ARITMETICAS = {T.SUMA, T.RESTA, T.MULTIPLICACION, T.DIVISION, T.MODULO}


def tipo_literal(operando) -> str | None:
    if not isinstance(operando, str):
        return None
    if operando in ("true", "false"):
        return BOOLEANO
    if operando == "null":
        return NULO
    if operando.startswith('"'):
        return CADENA
    if _ENTERO.match(operando):
        return ENTERO
    if _FLOTANTE.match(operando):
        return FLOTANTE
    return None


def es_literal(operando) -> bool:
    return tipo_literal(operando) is not None


class InferenciaTipos:
    """Tipos de direcciones, retornos y atributos, sacados de la tabla."""

    def __init__(self, tabla, resumen):
        self.globales: dict[str, str] = {}
        self.por_funcion: dict[str, dict] = {}
        self.retornos: dict[str, str] = {}
        self.atributos: dict[str, dict] = {}     # clase -> {campo: tipo}
        self.padres: dict[str, str] = {}
        self.clases = set(resumen.clases)

        global_scope = tabla.global_scope
        self._recorrer_globales(global_scope)
        for nombre, registro in resumen.registros.items():
            tipos = {}
            for simbolo in list(registro.parametros) + list(registro.locales):
                if simbolo.direccion:
                    tipos[simbolo.direccion] = simbolo.type
            self.por_funcion[nombre] = tipos
        self._recorrer_funciones(global_scope, "")

    def _recorrer_globales(self, scope) -> None:
        for simbolo in scope.symbols.values():
            if getattr(simbolo, "area", None) == "global" and simbolo.direccion:
                self.globales[simbolo.direccion] = simbolo.type
        for hijo in scope.children:
            if hijo.kind == "block":
                self._recorrer_globales(hijo)

    def _recorrer_funciones(self, scope, prefijo) -> None:
        for hijo in scope.children:
            if hijo.kind == "function":
                nombre = f"{prefijo}{hijo.name}"
                simbolo = scope.resolve_local(hijo.name)
                if simbolo is not None:
                    self.retornos[nombre] = simbolo.type
                self._recorrer_funciones(hijo, f"{nombre}.")
            elif hijo.kind == "class":
                clase = scope.resolve_local(hijo.name)
                if clase is not None and clase.extra.get("parent"):
                    self.padres[hijo.name] = clase.extra["parent"]
                self.atributos[hijo.name] = {
                    s.name: s.type for s in hijo.symbols.values()
                    if s.kind in ("variable", "constant")}
                self._recorrer_funciones(hijo, f"{hijo.name}.")
            elif hijo.kind == "block":
                self._recorrer_funciones(hijo, prefijo)

    def tipo_atributo(self, clase, campo) -> str | None:
        while clase is not None:
            tipo = self.atributos.get(clase, {}).get(campo)
            if tipo is not None:
                return tipo
            clase = self.padres.get(clase)
        return None

    def tipo_de(self, operando, funcion: str, temporales: dict) -> str | None:
        """Tipo de un operando dentro de la unidad `funcion`."""
        if operando is None:
            return None
        literal = tipo_literal(operando)
        if literal is not None:
            return literal
        if operando in temporales:
            return temporales[operando]
        if operando.startswith("global+"):
            return self.globales.get(operando)
        if operando.startswith("fp+"):
            return self.por_funcion.get(funcion, {}).get(operando)
        if operando == "this" and "." in funcion:
            return funcion.rsplit(".", 1)[0]
        return None

    def tipo_resultado(self, c, funcion: str, temporales: dict) -> str | None:
        """Tipo del valor que produce el cuádruplo `c`."""
        tipo = lambda op: self.tipo_de(op, funcion, temporales)
        if c.op == T.ASIGNAR:
            return tipo(c.arg1)
        if c.op in RELACIONALES or c.op in LOGICAS or c.op == T.NEGACION:
            return BOOLEANO
        if c.op in ARITMETICAS:
            izquierda, derecha = tipo(c.arg1), tipo(c.arg2)
            if c.op == T.SUMA and CADENA in (izquierda, derecha):
                return CADENA
            if FLOTANTE in (izquierda, derecha):
                return FLOTANTE
            return ENTERO
        if c.op == T.NEGATIVO:
            return tipo(c.arg1)
        if c.op == T.LLAMAR:
            return self.retornos.get(c.arg1)
        if c.op == T.LONGITUD:
            return ENTERO
        if c.op == T.NUEVO:
            return c.arg1
        if c.op == T.NUEVO_ARREGLO:
            return "[]"
        if c.op == T.LEER_INDICE:
            arreglo = tipo(c.arg1)
            if isinstance(arreglo, str) and arreglo.endswith("[]") and arreglo != "[]":
                return arreglo[:-2]
            return None
        if c.op == T.LEER_CAMPO:
            return self.tipo_atributo(tipo(c.arg1), c.arg2)
        return None


def es_byte(tipo) -> bool:
    """Los boolean ocupan un byte en memoria (lbu/sb)."""
    return tamano_de(tipo) == 1
