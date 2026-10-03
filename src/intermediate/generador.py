"""
Infraestructura del generador de código intermedio.

Junta el programa TAC, el pool de temporales y el generador de etiquetas, y
resuelve el punto donde se cruzan: el registro de activación. No recorre el
árbol de ANTLR; eso lo hace el listener de generación, igual que
SemanticListener recorre y llama a SemanticChecker:

    class ListenerTAC(CompiscriptListener):
        def exitAdditiveExpr(self, ctx):
            destino = self.gen.temporal_para(izq, der)
            self.gen.programa.emitir_binaria("+", izq, der, destino)
"""

from __future__ import annotations

from memoria import asignar_direcciones
from tac import ProgramaTAC
from temporales import GeneradorEtiquetas, PoolTemporales


class GeneradorTAC:
    """Estado compartido por toda la generación de código intermedio."""

    def __init__(self, tabla, resumen=None):
        self.tabla = tabla
        # Las direcciones se calculan antes de emitir nada: traducir un acceso a
        # variable necesita saber dónde vive.
        self.resumen = resumen if resumen is not None else asignar_direcciones(tabla)

        self.programa = ProgramaTAC()
        self.etiquetas = GeneradorEtiquetas()
        self._pools = [PoolTemporales()]   # el de abajo es el del código global
        self._contexto: list[str] = []     # clases y funciones abiertas

    @property
    def temporales(self) -> PoolTemporales:
        return self._pools[-1]

    def nuevo_temporal(self) -> str:
        return self.temporales.nuevo()

    def liberar(self, *operandos) -> None:
        for operando in operandos:
            self.temporales.liberar(operando)

    def temporal_para(self, *operandos) -> str:
        """Libera los operandos consumidos y entrega el temporal del resultado."""
        return self.temporales.temporal_para(*operandos)

    def es_temporal(self, nombre) -> bool:
        return self.temporales.es_temporal(nombre)

    def nueva_etiqueta(self, pista: str | None = None) -> str:
        return self.etiquetas.nueva(pista)

    def nombre_cualificado(self, nombre: str) -> str:
        """'suma', 'Empleado.sumar', 'contador.interno'.

        Mismo esquema que memoria.asignar_direcciones, para poder encontrar el
        registro de activación de una función por su nombre.
        """
        return ".".join(self._contexto + [nombre])

    def entrar_clase(self, nombre: str) -> None:
        self._contexto.append(nombre)

    def salir_clase(self) -> None:
        self._contexto.pop()

    def entrar_funcion(self, nombre: str) -> str:
        """Abre el cuerpo de una función y le da pool propio.

        Los temporales de una función viven en SU marco, pero al terminar una
        función anidada hay que seguir con los que la externa tenía vivos; por
        eso los pools se apilan en vez de reiniciarse.
        """
        cualificado = self.nombre_cualificado(nombre)
        self.programa.emitir_inicio_funcion(cualificado)
        self._contexto.append(nombre)
        self._pools.append(PoolTemporales())
        return cualificado

    def salir_funcion(self) -> str:
        """Cierra el cuerpo y reserva en su marco el pico de temporales usado."""
        cualificado = ".".join(self._contexto)
        pool = self._pools.pop()
        self._contexto.pop()

        registro = self.resumen.registros.get(cualificado)
        if registro is not None:
            registro.fijar_temporales(pool.pico)

        self.programa.emitir_fin_funcion(cualificado)
        return cualificado

    def registro_de(self, nombre_cualificado: str):
        return self.resumen.registros.get(nombre_cualificado)

    def estadisticas(self) -> dict:
        """Reciclaje en el ámbito global; el de cada función queda en su marco."""
        return self._pools[0].estadisticas()


def generar_codigo_intermedio(tabla, arbol) -> GeneradorTAC:
    """Punto de entrada de la fase de generación.

    PRECONDICIÓN: el enunciado prohíbe generar representación intermedia si hay
    algún error léxico, sintáctico o semántico. El pipeline lo verifica en
    analizar_codigo().
    """
    generador = GeneradorTAC(tabla)
    _traducir(generador, arbol)
    return generador


def _traducir(generador: GeneradorTAC, arbol) -> None:
    """Recorre el árbol emitiendo TAC.

    Todavía sin implementar: aquí enganchan las Personas 2 (expresiones, control
    de flujo, funciones) y 3 (arreglos, clases, herencia):

        from antlr4 import ParseTreeWalker
        from listener_tac import ListenerTAC
        ParseTreeWalker.DEFAULT.walk(ListenerTAC(generador), arbol)
    """
    return None
