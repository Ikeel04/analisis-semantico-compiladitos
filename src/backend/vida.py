"""
Análisis de vida para la selección de registros.

Los temporales se analizan entre bloques (flujo de datos hacia atrás hasta un
punto fijo): un temporal sigue vivo al salir de un bloque si algún sucesor lo
lee antes de redefinirlo. Las variables del programa se suponen siempre vivas
al salir, porque otra función o una vuelta del ciclo puede leerlas de memoria.
"""

from __future__ import annotations

from unidades import (
    bloques_basicos,
    definicion,
    es_direccion,
    es_temporal,
    usos,
)


class InfoVida:
    def __init__(self, unidad):
        self.unidad = unidad
        self.bloques = bloques_basicos(unidad)
        self.bloque_de: dict[int, object] = {}
        for b in self.bloques:
            for pos in b.posiciones:
                self.bloque_de[pos] = b

        self.entrada: dict[int, set] = {b.numero: set() for b in self.bloques}
        self.salida: dict[int, set] = {b.numero: set() for b in self.bloques}
        self._resolver()

        # Para cada posición, los temporales vivos justo después de ejecutarla.
        self._vivos_despues: dict[int, set] = {}
        for b in self.bloques:
            vivos = set(self.salida[b.numero])
            for pos in reversed(b.posiciones):
                self._vivos_despues[pos] = set(vivos)
                _, c = unidad.instrucciones[pos]
                definido = definicion(c)
                if es_temporal(definido):
                    vivos.discard(definido)
                for usado in usos(c):
                    if es_temporal(usado):
                        vivos.add(usado)

    def _usa_define(self, bloque) -> tuple[set, set]:
        """Temporales leídos antes de escribirse (usa) y escritos (define)."""
        usa, define = set(), set()
        for pos in bloque.posiciones:
            _, c = self.unidad.instrucciones[pos]
            for usado in usos(c):
                if es_temporal(usado) and usado not in define:
                    usa.add(usado)
            definido = definicion(c)
            if es_temporal(definido):
                define.add(definido)
        return usa, define

    def _resolver(self) -> None:
        usa_define = {b.numero: self._usa_define(b) for b in self.bloques}
        cambio = True
        while cambio:
            cambio = False
            for b in reversed(self.bloques):
                salida = set()
                for s in b.sucesores:
                    salida |= self.entrada[s]
                usa, define = usa_define[b.numero]
                entrada = usa | (salida - define)
                if salida != self.salida[b.numero] or entrada != self.entrada[b.numero]:
                    self.salida[b.numero] = salida
                    self.entrada[b.numero] = entrada
                    cambio = True

    def vivo_despues(self, nombre: str, pos: int) -> bool:
        """¿Hace falta el valor de `nombre` después de la instrucción `pos`?"""
        if es_direccion(nombre):
            return True
        return nombre in self._vivos_despues.get(pos, ())

    def vivos_al_salir(self, pos: int) -> set:
        """Temporales vivos al salir del bloque que contiene `pos`."""
        return self.salida[self.bloque_de[pos].numero]

    def es_inicio_de_bloque(self, pos: int) -> bool:
        return self.bloque_de[pos].posiciones[0] == pos

    def es_fin_de_bloque(self, pos: int) -> bool:
        return self.bloque_de[pos].posiciones[-1] == pos
