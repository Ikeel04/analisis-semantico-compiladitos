"""
Asignación y reciclaje de variables temporales, y generación de etiquetas.

Un temporal solo está vivo entre que se escribe y que se consume: apenas un
cuádruplo lo usa como argumento, el nombre vuelve a una bolsa de libres y se
reutiliza. Así (a+b)*(c+d)-(e+f) usa 2 temporales en vez de 5, que es espacio
que cada llamada deja de reservar en su registro de activación.

El algoritmo completo y su justificación están en docs/DISENO_TAC.md.
"""

from __future__ import annotations

PREFIJO_TEMPORAL = "t"
PREFIJO_ETIQUETA = "L"


class PoolTemporales:
    """Administra los nombres t1, t2, ... reutilizando los que quedan libres."""

    def __init__(self, prefijo: str = PREFIJO_TEMPORAL):
        self.prefijo = prefijo
        self._creados = 0
        self._libres: list[str] = []
        self._ocupados: set[str] = set()
        self.pico = 0                # máximo de temporales vivos a la vez
        self.reutilizaciones = 0

    def nuevo(self) -> str:
        """Entrega un temporal libre; solo inventa un nombre si no queda ninguno."""
        if self._libres:
            nombre = self._libres.pop()      # LIFO: el liberado más reciente
            self.reutilizaciones += 1
        else:
            self._creados += 1
            nombre = f"{self.prefijo}{self._creados}"
        self._ocupados.add(nombre)
        self.pico = max(self.pico, len(self._ocupados))
        return nombre

    def liberar(self, nombre) -> bool:
        """Devuelve un temporal a la bolsa de libres.

        Es tolerante a propósito: el generador le pasa cualquier operando sin
        revisar qué es, y aquí se ignora lo que no sea un temporal ocupado. El
        False también cubre la doble liberación, que dejaría el nombre repetido
        en la bolsa y haría que dos valores distintos se pisen.
        """
        if not self.es_temporal(nombre) or nombre not in self._ocupados:
            return False
        self._ocupados.discard(nombre)
        self._libres.append(nombre)
        return True

    def temporal_para(self, *operandos) -> str:
        """Libera los operandos ya consumidos y entrega el temporal del resultado.

            destino = pool.temporal_para(izquierda, derecha)
            programa.emitir_binaria("+", izquierda, derecha, destino)

        Liberar antes de pedir es válido porque un cuádruplo lee sus argumentos
        antes de escribir el resultado. Se libera de derecha a izquierda para que
        quede arriba de la pila el operando izquierdo: la salida sale
        `t1 = t1 * t2`, que es la forma más fácil de revisar a mano.
        """
        for operando in reversed(operandos):
            self.liberar(operando)
        return self.nuevo()

    def es_temporal(self, nombre) -> bool:
        """True si el nombre lo generó este pool (tN), no una variable del fuente."""
        if not isinstance(nombre, str) or not nombre.startswith(self.prefijo):
            return False
        return nombre[len(self.prefijo):].isdigit()

    @property
    def vivos(self) -> int:
        return len(self._ocupados)

    @property
    def creados(self) -> int:
        """Cuántos nombres distintos existen: el tamaño que hay que reservar."""
        return self._creados

    def reiniciar(self) -> None:
        self._creados = 0
        self._libres.clear()
        self._ocupados.clear()
        self.pico = 0
        self.reutilizaciones = 0

    def estadisticas(self) -> dict:
        pedidos = self._creados + self.reutilizaciones
        return {
            "temporales_pedidos": pedidos,
            "nombres_creados": self._creados,
            "reutilizaciones": self.reutilizaciones,
            "pico_simultaneo": self.pico,
            "vivos_al_final": len(self._ocupados),
            "ahorro": pedidos - self._creados,
        }


class GeneradorEtiquetas:
    """Entrega etiquetas únicas L1, L2, ... para saltos y bloques.

    No se reciclan: una etiqueta es una posición del programa, y reutilizar el
    nombre haría que un salto aterrizara en el lugar equivocado.
    """

    def __init__(self, prefijo: str = PREFIJO_ETIQUETA):
        self.prefijo = prefijo
        self._creadas = 0

    def nueva(self, pista: str | None = None) -> str:
        """`pista` agrega un sufijo legible: L3_fin_while."""
        self._creadas += 1
        etiqueta = f"{self.prefijo}{self._creadas}"
        return f"{etiqueta}_{pista}" if pista else etiqueta

    @property
    def creadas(self) -> int:
        return self._creadas

    def reiniciar(self) -> None:
        self._creadas = 0
