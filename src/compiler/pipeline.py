"""Compilación unificada de Compiscript: análisis + código intermedio.

Corre los tres analizadores sobre el mismo código y junta sus errores en un
solo listado, ordenado por línea y columna y con un formato común listo para
mostrar en la interfaz:

    from pipeline import analizar_codigo

    resultado = analizar_codigo("ejemplo.cps", codigo)
    resultado.es_valido    # True si no hubo ningún error
    resultado.errores      # [FilaError(tipo, linea, columna, simbolo, descripcion), ...]
    resultado.tokens       # lista de Token (de lexico), para la tabla
    resultado.arbol        # árbol sintáctico como texto, para visualizarlo
    resultado.tac          # ProgramaTAC, o None si no se generó

Hay dos compuertas distintas: el análisis semántico corre si el sintáctico no
falló (sobre un árbol incompleto no tiene sentido chequear tipos), y la
generación de código intermedio corre solo si no hubo NINGÚN error de ningún
tipo, como exige el enunciado. La segunda es más estricta: basta un error
semántico, con el árbol perfecto, para no generar nada.
"""

import os
import sys
from dataclasses import dataclass, field

from antlr4 import ParseTreeWalker

# El resultado es flat (mismo estilo que los tests): cada paquete se importa
# poniendo su carpeta en sys.path. El pipeline se asegura de tener disponibles
# src/parser, src/lexico, src/semantic y src/intermediate sin que el punto de
# entrada lo haga.
_AQUI = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.dirname(_AQUI)
for _paquete in ("parser", "lexico", "semantic", "intermediate"):
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
from generador import generar_codigo_intermedio
from memoria import asignar_direcciones

# Mensaje que exige la especificación cuando el archivo no tiene errores.
MENSAJE_EXITO = (
    "El archivo se analizó correctamente: no se encontraron errores "
    "léxicos, sintácticos ni semánticos."
)

# Mensaje de la compuerta de generación, para mostrarlo en la pestaña de TAC.
MENSAJE_TAC_BLOQUEADO = (
    "No se generó código intermedio porque el programa tiene errores. "
    "La representación intermedia solo se produce cuando el análisis léxico, "
    "sintáctico y semántico termina sin reportar ninguno."
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
    tabla: object = None               # SymbolTable, o None si no se analizó.

    # Código intermedio. Queda todo vacío si la compuerta no dejó generar.
    tac: object = None                 # ProgramaTAC
    tac_texto: str = ""
    tac_filas: list[dict] = field(default_factory=list)    # vista de cuádruplos
    memoria: object = None             # ResumenMemoria
    memoria_filas: list[dict] = field(default_factory=list)
    memoria_texto: str = ""
    temporales: dict = field(default_factory=dict)         # métricas del reciclaje

    @property
    def es_valido(self) -> bool:
        """True si no se encontró ningún error léxico, sintáctico o semántico."""
        return not self.errores

    @property
    def genero_tac(self) -> bool:
        """True si la compuerta dejó pasar y se produjo código intermedio."""
        return self.tac is not None


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

    tabla = None
    if sintactico.es_valido and sintactico.arbol is not None:
        listener = SemanticListener()
        ParseTreeWalker.DEFAULT.walk(listener, sintactico.arbol)
        errores += [
            FilaError("Semántico", e.line, e.column, "", e.message)
            for e in listener.checker.errors.issues
        ]
        tabla = listener.checker.table

    errores.sort(key=lambda e: (e.linea, e.columna, e.tipo))

    resultado = ResultadoAnalisis(
        nombre=nombre,
        errores=errores,
        tokens=lexico.tokens,
        arbol=arbol_a_texto(sintactico.arbol),
        arbol_estructura=arbol_a_estructura(sintactico.arbol),
    )

    if tabla is None:
        return resultado

    # Compuerta: sin errores de ningún tipo, se genera el intermedio.
    if not errores:
        generador = generar_codigo_intermedio(tabla, sintactico.arbol)
        resultado.tac = generador.programa
        resultado.tac_texto = generador.programa.como_texto(numerar=True)
        resultado.tac_filas = generador.programa.filas_para_ide()
        resultado.memoria = generador.resumen
        resultado.memoria_filas = generador.resumen.filas_para_ide()
        resultado.memoria_texto = generador.resumen.describe()
        resultado.temporales = generador.estadisticas()
    else:
        # Las direcciones no son código intermedio sino información de la tabla
        # de símbolos, así que se calculan aunque el programa no compile.
        asignar_direcciones(tabla)

    resultado.tabla = tabla
    resultado.ambitos = tabla.filas_para_ide()
    resultado.ambitos_texto = tabla.describe_tree()
    return resultado