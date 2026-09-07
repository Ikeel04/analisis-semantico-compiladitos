"""Representación y recolección de los errores sintácticos de Compiscript.

Igual que en lexico/errores.py: el parser que genera ANTLR reporta sus
propios errores imprimiéndolos en consola y en inglés (p. ej. "mismatched
input ';' expecting {...}"). Aquí se sustituye ese comportamiento por un
ErrorListener propio que los guarda en una lista y arma un mensaje en
español a partir del símbolo encontrado y del conjunto de símbolos que el
parser esperaba en ese punto.
"""

from dataclasses import dataclass

from antlr4 import Token
from antlr4.error.ErrorListener import ErrorListener

LIMITE_SUGERENCIAS = 6


@dataclass
class ErrorSintactico:
    """Un error sintáctico ya traducido y listo para mostrarse al usuario."""

    linea: int
    columna: int
    simbolo: str
    descripcion: str

    tipo = "Sintáctico"

    def __str__(self) -> str:
        return (f"[{self.tipo}] Línea {self.linea}, columna {self.columna}: "
                f"{self.descripcion}")


def _nombre_del_token(recognizer, tipo: int) -> str:
    """Nombre legible de un tipo de token, a partir del vocabulario del parser.

    A diferencia del lexer, en el parser no sirve usar ruleNames (esas son
    las reglas gramaticales, no los tokens). Lo correcto es literalNames
    ('let', ';', '+'...) y, si el token no es literal, symbolicNames
    (Identifier, Literal...).
    """
    if tipo == Token.EOF:
        return "el final del archivo"
    if 0 <= tipo < len(recognizer.literalNames) and recognizer.literalNames[tipo] != "<INVALID>":
        return recognizer.literalNames[tipo].strip("'")
    if 0 <= tipo < len(recognizer.symbolicNames) and recognizer.symbolicNames[tipo] != "<INVALID>":
        return recognizer.symbolicNames[tipo]
    return f"token#{tipo}"


def _tokens_esperados(recognizer) -> list[str]:
    """Nombres, sin repetir, de los tokens válidos en el punto del error.

    El runtime de Python representa el IntervalSet de expectedTokens como una
    lista de `range` en `.intervals` (no trae un `.toList()` como la versión
    de Java), así que hay que recorrerlos a mano.
    """
    nombres = []
    vistos = set()
    for intervalo in recognizer.getExpectedTokens().intervals or []:
        for tipo in intervalo:
            nombre = _nombre_del_token(recognizer, tipo)
            if nombre not in vistos:
                vistos.add(nombre)
                nombres.append(nombre)
    return nombres


def _listar(nombres: list[str]) -> str:
    """Convierte una lista de nombres en una enumeración en español."""
    if len(nombres) > LIMITE_SUGERENCIAS:
        return (", ".join(nombres[:LIMITE_SUGERENCIAS])
                + f", entre otros ({len(nombres)} posibles)")
    if len(nombres) == 1:
        return nombres[0]
    return ", ".join(nombres[:-1]) + " o " + nombres[-1]


def _describir(recognizer, offending_symbol) -> str:
    """Arma la descripción en español: qué se encontró y qué se esperaba."""
    if offending_symbol is not None and offending_symbol.type == Token.EOF:
        base = "el archivo terminó de forma inesperada"
    elif offending_symbol is not None:
        base = f"se encontró '{offending_symbol.text}', lo cual no es válido aquí"
    else:
        base = "hay una entrada no válida en este punto"

    esperados = _tokens_esperados(recognizer)
    if esperados:
        return f"{base}; se esperaba {_listar(esperados)}"
    return base


class ColectorErroresSintacticos(ErrorListener):
    """ErrorListener que acumula los errores del parser en vez de imprimirlos."""

    def __init__(self):
        super().__init__()
        self.errores: list[ErrorSintactico] = []
        # (línea, columna, símbolo) del último error reportado, para no
        # repetir el mismo mensaje si ANTLR reintenta en el mismo punto
        # durante la recuperación.
        self._ultimo: tuple[int, int, str] | None = None

    def syntaxError(self, recognizer, offendingSymbol, linea, columna, mensaje, excepcion):
        columna += 1  # ANTLR cuenta las columnas desde 0; el usuario, desde 1.
        simbolo = offendingSymbol.text if offendingSymbol is not None else ""

        clave = (linea, columna, simbolo)
        if clave == self._ultimo:
            return
        self._ultimo = clave

        descripcion = _describir(recognizer, offendingSymbol)
        self.errores.append(ErrorSintactico(linea, columna, simbolo, descripcion))
