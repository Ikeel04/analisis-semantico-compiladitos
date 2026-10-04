"""
Los ejemplos de ejemplos/ son los archivos de prueba de la defensa: cada
programa válido debe compilar sin errores, generar código intermedio completo
(sin construcciones pendientes) y no dejar temporales vivos; cada programa con
errores no debe generar nada.

Corre con: python -m unittest discover -s tests -v
"""

import glob
import os
import sys
import unittest

_BASE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(_BASE, "..", "src", "compiler"))

from pipeline import analizar_codigo

RUTA_EJEMPLOS = os.path.join(_BASE, "..", "ejemplos")


def _leer(ruta):
    with open(ruta, encoding="utf-8") as archivo:
        return archivo.read()


def _ejemplos(patron):
    return sorted(glob.glob(os.path.join(RUTA_EJEMPLOS, patron)))


class TestEjemplosValidos(unittest.TestCase):

    def test_hay_ejemplos_por_cada_item_de_la_rubrica(self):
        nombres = {os.path.basename(r) for r in _ejemplos("tac_*.cps")}
        self.assertGreaterEqual(len(nombres), 8)

    def test_todo_ejemplo_valido_genera_codigo_intermedio_completo(self):
        rutas = _ejemplos("ok_*.cps") + _ejemplos("tac_*.cps")
        self.assertGreater(len(rutas), 0)
        for ruta in rutas:
            with self.subTest(ejemplo=os.path.basename(ruta)):
                r = analizar_codigo(os.path.basename(ruta), _leer(ruta))
                self.assertTrue(r.es_valido, [str(e) for e in r.errores])
                self.assertTrue(r.genero_tac)
                self.assertGreater(len(r.tac_filas), 0)
                self.assertNotIn("pendiente", r.tac_texto)
                self.assertNotIn("/*", r.tac_texto)
                self.assertEqual(r.temporales["vivos_al_final"], 0)


class TestEjemplosConErrores(unittest.TestCase):

    def test_ningun_ejemplo_con_errores_genera_codigo_intermedio(self):
        rutas = _ejemplos("errores_*.cps")
        self.assertGreater(len(rutas), 0)
        for ruta in rutas:
            with self.subTest(ejemplo=os.path.basename(ruta)):
                r = analizar_codigo(os.path.basename(ruta), _leer(ruta))
                self.assertFalse(r.es_valido)
                self.assertFalse(r.genero_tac)
                self.assertEqual(r.tac_texto, "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
