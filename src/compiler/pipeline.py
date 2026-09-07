"""Análisis unificado (léxico + sintáctico + semántico) de Compiscript.

Corre los tres analizadores sobre el mismo código y junta sus errores en un
solo listado, ordenado por línea y columna y con un formato común listo para
mostrar en la interfaz:

    from pipeline import analizar_codigo

    resultado = analizar_codigo("ejemplo.cps", codigo)
    resultado.es_valido    # True si no hubo errores léxicos ni sintácticos
    resultado.errores      # [FilaError(tipo, linea, columna, simbolo, descripcion), ...]
    resultado.tokens       # lista de Token (de lexico), para la tabla
    resultado.arbol        # árbol sintáctico como texto, para visualizarlo

El análisis semántico (listener.py + checker.py) se ejecuta solo cuando el
código pasó el análisis sintáctico: con un árbol incompleto no tiene sentido
reportar errores de tipos sobre nodos mal formados.
"""

import os
import sys
from dataclasses import dataclass, field

from antlr4 import ParseTreeWalker

# El resultado es flat (mismo estilo que los tests): cada paquete se importa
# poniendo su carpeta en sys.path. El pipeline se asegura de tener disponibles
# src/parser, src/lexico y src/semantic sin que el punto de entrada lo haga.
_AQUI = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.dirname(_AQUI)
for _paquete in ("parser", "lexico", "semantic"):
    _ruta = os.path.join(_SRC, _paquete)
    if _ruta not in sys.path:
        sys.path.insert(0, _ruta)

from analizador import Token, analizar_texto as analizar_texto_lexico
from parse import (
    analizar_texto as analizar_texto_sintactico,
    arbol_a_estructura,
    arbol_a_texto,
)
from listener import SemanticListener

# Mensaje que exige la especificación cuando el archivo no tiene errores.
MENSAJE_EXITO = (
    "El archivo se analizó correctamente: no se encontraron errores "
    "léxicos, sintácticos ni semánticos."
)


@dataclass
class FilaError:
    """Un error (léxico, sintáctico o semántico) con el formato común."""

    tipo: str      # "Léxico", "Sintáctico" o "Semántico".
    linea: int
    columna: int
    simbolo: str   # Lexema, símbolo o descripción relacionada con el error.
    descripcion: str

    def __str__(self) -> str:
        return f"[{self.tipo}] Línea {self.linea}, columna {self.columna}: {self.descripcion}"


@dataclass
class ResultadoAnalisis:
    """Salida completa del análisis léxico, sintáctico y semántico."""

    nombre: str
    errores: list[FilaError] = field(default_factory=list)
    tokens: list[Token] = field(default_factory=list)
    arbol: str = ""                    # Árbol como texto (notación con paréntesis).
    arbol_estructura: list = None      # [texto, [hijos]] para dibujarlo como imagen.
    ambitos: list[dict] = field(default_factory=list)  # filas de la pestaña Ámbitos.
    ambitos_texto: str = ""            # descripción textual del árbol de ámbitos.

    @property
    def es_valido(self) -> bool:
        """True si no se encontró ningún error léxico, sintáctico o semántico."""
        return not self.errores


def analizar_codigo(nombre: str, codigo: str) -> ResultadoAnalisis:
    """Analiza código Compiscript con los tres analizadores y junta los errores."""
    lexico = analizar_texto_lexico(codigo)
    sintactico = analizar_texto_sintactico(codigo)

    errores = [
        FilaError("Léxico", e.linea, e.columna, e.lexema, e.descripcion)
        for e in lexico.errores
    ]
    errores += [
        FilaError("Sintáctico", e.linea, e.columna, e.simbolo, e.descripcion)
        for e in sintactico.errores
    ]

    if sintactico.es_valido and sintactico.arbol is not None:
        listener = SemanticListener()
        ParseTreeWalker.DEFAULT.walk(listener, sintactico.arbol)
        errores += [
            FilaError("Semántico", e.line, e.column, "", e.message)
            for e in listener.checker.errors.issues
        ]
        ambitos = listener.checker.table.filas_para_ide()
        ambitos_texto = listener.checker.table.describe_tree()
    else:
        ambitos = []
        ambitos_texto = ""

    errores.sort(key=lambda e: (e.linea, e.columna, e.tipo))

    return ResultadoAnalisis(
        nombre=nombre,
        errores=errores,
        tokens=lexico.tokens,
        arbol=arbol_a_texto(sintactico.arbol),
        arbol_estructura=arbol_a_estructura(sintactico.arbol),
        ambitos=ambitos,
        ambitos_texto=ambitos_texto,
    )