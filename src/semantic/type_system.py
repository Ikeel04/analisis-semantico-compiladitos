"""
Sistema de tipos de Compiscript.

Reglas puras de compatibilidad: no conocen ANTLR ni la tabla de símbolos.

Las funciones de operadores devuelven el tipo del resultado
o None cuando la operación no es válida; quien llama decide el mensaje.

ERROR es un tipo especial: cuando una regla falla, el chequeo devuelve ERROR y
las reglas siguientes lo dejan pasar en silencio, de modo que un solo error no
produce una cascada de mensajes derivados.

El módulo se llama type_system y no types para no chocar con el módulo types
de la librería estándar de Python.
"""

from __future__ import annotations

INTEGER = "integer"
FLOAT = "float"     # el lenguaje aún no lo genera, pero el requerimiento lo menciona
STRING = "string"
BOOLEAN = "boolean"
NULL = "null"
VOID = "void"       # funciones sin tipo de retorno declarado
ERROR = "<error>"

BUILTIN = {INTEGER, FLOAT, STRING, BOOLEAN, NULL, VOID}
NUMERIC = {INTEGER, FLOAT}


#consultas sobre un tipo 

def is_error(type_) -> bool:
    """None (tipo aún no inferido) y ERROR se tratan igual: silencio."""
    return type_ is None or type_ == ERROR


def is_array(type_) -> bool:
    return isinstance(type_, str) and type_.endswith("[]")


def array_of(type_: str) -> str:
    return f"{type_}[]"


def element_type(type_) -> str:
    return type_[:-2] if is_array(type_) else ERROR


def is_numeric(type_) -> bool:
    return type_ in NUMERIC


def is_class(type_) -> bool:
    """Tipo definido por el usuario (una clase), no primitivo ni arreglo."""
    return isinstance(type_, str) and type_ not in BUILTIN and type_ != ERROR and not is_array(type_)


def is_nullable(type_) -> bool:
    """Solo clases y arreglos pueden valer null."""
    return is_array(type_) or is_class(type_)


def name(type_) -> str:
    """Nombre legible para los mensajes de error."""
    return type_ if isinstance(type_, str) and type_ != ERROR else "desconocido"


#compatibilidad 

def assignable(target, value, is_subclass=None) -> bool:
    """¿Un valor de tipo `value` cabe en un destino de tipo `target`?

    is_subclass(hijo, padre) -> bool es un hook opcional para la herencia de
    clases; sin él, las clases solo son compatibles consigo mismas.
    """
    if is_error(target) or is_error(value):
        return True
    if target == value:
        return True
    if value == NULL:
        return is_nullable(target)
    if target == FLOAT and value == INTEGER:
        return True
    if is_array(target) and is_array(value):
        if element_type(value) == NULL:   # arreglo literal vacío
            return True
        return assignable(element_type(target), element_type(value), is_subclass)
    if is_subclass and is_class(target) and is_class(value):
        return is_subclass(value, target)
    return False


def comparable(left, right, is_subclass=None) -> bool:
    """Tipos que se pueden comparar con == y !=."""
    if is_error(left) or is_error(right):
        return True
    if left == right:
        return True
    if is_numeric(left) and is_numeric(right):
        return True
    if left == NULL:
        return is_nullable(right)
    if right == NULL:
        return is_nullable(left)
    return assignable(left, right, is_subclass) or assignable(right, left, is_subclass)


def unify(types: list) -> str | None:
    """Tipo común de los elementos de un arreglo literal.
    Devuelve None si los elementos son incompatibles entre sí.
    """
    result = NULL
    for current in types:
        if is_error(current):
            return ERROR
        if result == NULL:
            result = current
        elif current == NULL or assignable(result, current):
            continue
        elif assignable(current, result):
            result = current
        else:
            return None
    return result


#operadores

def arithmetic(op: str, left, right):
    """+, -, *, / y %: numéricos; + también concatena string con string."""
    if is_error(left) or is_error(right):
        return ERROR
    if op == "+" and left == STRING and right == STRING:
        return STRING
    if is_numeric(left) and is_numeric(right):
        return FLOAT if FLOAT in (left, right) else INTEGER
    return None


def logical(op: str, left, right):
    """&& y ||: ambos operandos boolean."""
    if is_error(left) or is_error(right):
        return ERROR
    return BOOLEAN if left == BOOLEAN and right == BOOLEAN else None


def comparison(op: str, left, right, is_subclass=None):
    """== y != entre tipos comparables; <, <=, > y >= solo entre numéricos."""
    if is_error(left) or is_error(right):
        return ERROR
    if op in ("==", "!="):
        return BOOLEAN if comparable(left, right, is_subclass) else None
    return BOOLEAN if is_numeric(left) and is_numeric(right) else None


def unary(op: str, operand):
    """! sobre boolean, - sobre numéricos."""
    if is_error(operand):
        return ERROR
    if op == "!":
        return BOOLEAN if operand == BOOLEAN else None
    if op == "-":
        return operand if is_numeric(operand) else None
    return None
