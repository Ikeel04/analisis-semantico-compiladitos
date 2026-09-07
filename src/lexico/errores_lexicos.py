"""Representación y recolección de los errores léxicos de Compiscript.

El lexer que genera ANTLR reporta sus errores imprimiéndolos en consola y en
inglés. Aquí se sustituye ese comportamiento por un ErrorListener propio que
los guarda en una lista y los traduce a mensajes comprensibles en español.
"""

from dataclasses import dataclass

from antlr4.error.ErrorListener import ErrorListener


@dataclass
class ErrorLexico:
    """Un error léxico ya traducido y listo para mostrarse al usuario."""

    linea: int
    columna: int
    lexema: str
    descripcion: str

    tipo = "Léxico"

    def __str__(self) -> str:
        return (f"[{self.tipo}] Línea {self.linea}, columna {self.columna}: "
                f"{self.descripcion} (se encontró: {self.lexema!r})")


# Pistas para los símbolos que se escriben mal con más frecuencia.
_SUGERENCIAS = {
    "'": 'las cadenas de texto se escriben con comillas dobles: "texto"',
    "&": "el operador lógico Y se escribe con dos símbolos: &&",
    "|": "el operador lógico O se escribe con dos símbolos: ||",
    "#": "los comentarios se escriben con // o con /* */",
}


def _describir(lexema: str) -> str:
    """Traduce un lexema no reconocido a una explicación en español."""
    if lexema.startswith('"'):
        return "cadena de texto sin cerrar: falta la comilla doble final"
    if lexema in _SUGERENCIAS:
        return f"símbolo no válido en Compiscript; {_SUGERENCIAS[lexema]}"
    if len(lexema) == 1:
        return "carácter no reconocido por el lenguaje"
    return "secuencia de caracteres no reconocida por el lenguaje"


def _texto_no_reconocido(lexer) -> str:
    """Fragmento de la entrada que el lexer no logró convertir en un token."""
    inicio = lexer._tokenStartCharIndex
    fin = lexer._input.index
    texto = lexer._input.getText(inicio, fin)
    return texto.rstrip() if texto.startswith('"') else texto[:1]


class ColectorErroresLexicos(ErrorListener):
    """ErrorListener que acumula los errores del lexer en vez de imprimirlos."""

    def __init__(self):
        super().__init__()
        self.errores: list[ErrorLexico] = []
        # Posición (línea, columna) donde terminó el error anterior.
        self._fin_anterior: tuple[int, int] | None = None

    def syntaxError(self, recognizer, simbolo, linea, columna, mensaje, excepcion):
        lexema = _texto_no_reconocido(recognizer)
        columna += 1  # ANTLR cuenta las columnas desde 0; el usuario, desde 1.

        if self._unir_con_anterior(linea, columna, lexema):
            return

        self.errores.append(ErrorLexico(linea, columna, lexema, _describir(lexema)))
        self._fin_anterior = (linea, columna + len(lexema))

    def _unir_con_anterior(self, linea: int, columna: int, lexema: str) -> bool:
        """Agrupa caracteres inválidos contiguos (`~~~`) en un solo error.

        Sin esto, ANTLR generaría un mensaje idéntico por cada carácter y el
        reporte se llenaría de líneas repetidas que no aportan información.
        """
        if not self.errores or self._fin_anterior != (linea, columna):
            return False

        anterior = self.errores[-1]
        if '"' in anterior.lexema or '"' in lexema:
            return False  # Una cadena sin cerrar merece su propio mensaje.

        anterior.lexema += lexema
        anterior.descripcion = _describir(anterior.lexema)
        self._fin_anterior = (linea, columna + len(lexema))
        return True
