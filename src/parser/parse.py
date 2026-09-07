"""Analizador sintáctico de Compiscript, construido sobre el parser que
genera ANTLR.

Punto de entrada para el resto del proyecto:

    from parse import analizar_texto

    resultado = analizar_texto(codigo)
    resultado.errores    # lista de ErrorSintactico, para el panel de errores
    resultado.es_valido  # True si no hubo ningún error sintáctico
    resultado.arbol      # ParserRuleContext de la regla 'program', por si
                          # luego se necesita recorrer el árbol (semántico)
"""

from dataclasses import dataclass, field
from pathlib import Path

from antlr4 import CommonTokenStream, InputStream

from generated.CompiscriptLexer import CompiscriptLexer
from generated.CompiscriptParser import CompiscriptParser
from errores_sintacticos import ColectorErroresSintacticos, ErrorSintactico

EXTENSION = ".cps"


@dataclass
class ResultadoSintactico:
    """Salida completa del análisis sintáctico de un texto."""

    arbol: object = None
    errores: list[ErrorSintactico] = field(default_factory=list)

    @property
    def es_valido(self) -> bool:
        """True si no se encontró ningún error sintáctico."""
        return not self.errores


def analizar_texto(codigo: str) -> ResultadoSintactico:
    """Parsea código Compiscript y devuelve el árbol y los errores sintácticos.

    Los errores léxicos no se reportan aquí (de eso se encarga el módulo
    lexico): el lexer se deja sin listeners para que no imprima nada en
    consola, y ante un carácter inválido simplemente lo descarta y sigue.
    """
    lexer = CompiscriptLexer(InputStream(codigo))
    lexer.removeErrorListeners()

    parser = CompiscriptParser(CommonTokenStream(lexer))
    colector = ColectorErroresSintacticos()
    parser.removeErrorListeners()  # El listener por defecto imprime en consola y en inglés.
    parser.addErrorListener(colector)

    # ANTLR usa DefaultErrorStrategy: ante un error hace un solo intento de
    # insertar o descartar un token, y si no puede, salta al siguiente punto
    # de sincronización (fin de la regla actual) y sigue parseando. Por eso
    # el análisis no se detiene en el primer error.
    arbol = parser.program()

    return ResultadoSintactico(arbol, colector.errores)


def analizar_archivo(ruta) -> ResultadoSintactico:
    """Igual que analizar_texto, pero leyendo un archivo .cps del disco.

    Lanza ValueError si la extensión no es .cps y OSError si no se puede leer.
    """
    ruta = Path(ruta)
    if ruta.suffix.lower() != EXTENSION:
        raise ValueError(
            f"El archivo debe tener extensión {EXTENSION}, pero se recibió '{ruta.name}'."
        )
    return analizar_texto(ruta.read_text(encoding="utf-8"))


def arbol_a_texto(arbol) -> str:
    """Árbol sintáctico en notación con paréntesis, para mostrarlo como texto."""
    if arbol is None:
        return ""
    return arbol.toStringTree(ruleNames=CompiscriptParser.ruleNames)


def arbol_a_estructura(nodo) -> list:
    """Convierte el árbol ANTLR en [texto, [hijos]] para poder dibujarlo.

    Las hojas son los tokens (su texto) y los nodos internos llevan el nombre
    de la regla gramatical que representan.
    """
    if nodo is None:
        return []
    if nodo.getChildCount() == 0:
        texto = nodo.getText()
        return [texto if texto else "<vacío>", []]
    texto = CompiscriptParser.ruleNames[nodo.getRuleIndex()]
    return [texto, [arbol_a_estructura(hijo) for hijo in nodo.getChildren()]]