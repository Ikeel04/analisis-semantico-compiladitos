"""Analizador léxico de Compiscript, construido sobre el lexer que genera ANTLR.

Punto de entrada para el resto del proyecto:

    from lexico import analizar_archivo

    resultado = analizar_archivo("ejemplos/valido.cps")
    resultado.tokens    # lista de Token, para la tabla de la interfaz
    resultado.errores   # lista de ErrorLexico, para el panel de errores
    resultado.es_valido # True si no hubo ningún error léxico
"""

from dataclasses import dataclass, field
from pathlib import Path

from antlr4 import InputStream

from generated.CompiscriptLexer import CompiscriptLexer
from errores_lexicos import ColectorErroresLexicos, ErrorLexico

EXTENSION = ".cps"


@dataclass
class Token:
    """Un token reconocido, con la información que se muestra en la interfaz."""

    tipo: str      # Nombre del token: "Identifier", "Literal", "let", "+"...
    lexema: str    # Texto exacto que apareció en el archivo fuente.
    linea: int
    columna: int


@dataclass
class ResultadoLexico:
    """Salida completa del análisis léxico de un archivo."""

    tokens: list[Token] = field(default_factory=list)
    errores: list[ErrorLexico] = field(default_factory=list)

    @property
    def es_valido(self) -> bool:
        """True si no se encontró ningún error léxico."""
        return not self.errores


def analizar_texto(codigo: str) -> ResultadoLexico:
    """Escanea código Compiscript y devuelve sus tokens y sus errores léxicos."""
    lexer = CompiscriptLexer(InputStream(codigo))
    colector = ColectorErroresLexicos()
    lexer.removeErrorListeners()  # El listener por defecto imprime en consola y en inglés.
    lexer.addErrorListener(colector)

    # getAllTokens() recorre la entrada completa: ante un carácter inválido
    # ANTLR lo descarta y continúa, por lo que el análisis no se detiene en el
    # primer error y se reportan todos en una misma ejecución.
    tokens = [_a_token(lexer, t) for t in lexer.getAllTokens()]
    return ResultadoLexico(tokens, colector.errores)


def analizar_archivo(ruta) -> ResultadoLexico:
    """Igual que analizar_texto, pero leyendo un archivo .cps del disco.

    Lanza ValueError si la extensión no es .cps y OSError si no se puede leer.
    """
    ruta = Path(ruta)
    if ruta.suffix.lower() != EXTENSION:
        raise ValueError(
            f"El archivo debe tener extensión {EXTENSION}, pero se recibió '{ruta.name}'."
        )
    return analizar_texto(ruta.read_text(encoding="utf-8"))


def _a_token(lexer: CompiscriptLexer, token) -> Token:
    """Convierte un token de ANTLR al Token simple que usa la interfaz."""
    return Token(
        tipo=_nombre_del_tipo(lexer, token.type),
        lexema=token.text,
        linea=token.line,
        columna=token.column + 1,  # ANTLR cuenta las columnas desde 0.
    )


def _nombre_del_tipo(lexer: CompiscriptLexer, tipo: int) -> str:
    """Nombre legible del token.

    ANTLR numera los tokens en dos grupos: primero los que aparecen escritos
    literalmente en la gramática ('let', '+', ';'), cuyo texto está en
    literalNames en la posición 'tipo'; y después las reglas léxicas con nombre
    propio (Literal, Identifier), que están en ruleNames en la posición
    'tipo - 1', porque los tipos de token empiezan en 1 y los índices en 0.
    """
    if tipo < len(lexer.literalNames):
        return lexer.literalNames[tipo].strip("'")
    if tipo - 1 < len(lexer.ruleNames):
        return lexer.ruleNames[tipo - 1]
    return f"token#{tipo}"
