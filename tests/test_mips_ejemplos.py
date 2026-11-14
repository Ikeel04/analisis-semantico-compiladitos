"""
Verificación de los ejemplos `ejemplos/asm_*.cps`.

Para cada ejemplo: compila sin errores, no deja instrucciones pendientes y la
salida esperada (la del intérprete del TAC) coincide con la de MARS, tanto con
el ensamblador optimizado como sin optimizar. Agregar un ejemplo nuevo
`asm_*.cps` basta para que quede cubierto.

Los tests que ejecutan MARS necesitan MARS_JAR (ver test_mips_traductor.py).

Corre con: python -m unittest discover -s tests -v
"""

import glob
import os
import unittest

from test_mips_traductor import MARS_JAR, ejecutar_en_mars

from pipeline import analizar_codigo

RUTA_EJEMPLOS = os.path.join(os.path.dirname(__file__), "..", "ejemplos")
EJEMPLOS = sorted(glob.glob(os.path.join(RUTA_EJEMPLOS, "asm_*.cps")))


def compilar_ejemplo(ruta):
    with open(ruta, encoding="utf-8") as fh:
        return analizar_codigo(os.path.basename(ruta), fh.read())


class TestEjemplosAsm(unittest.TestCase):

    def test_hay_ejemplos(self):
        self.assertTrue(EJEMPLOS)

    def test_compilan_sin_pendientes(self):
        for ruta in EJEMPLOS:
            with self.subTest(ejemplo=os.path.basename(ruta)):
                resultado = compilar_ejemplo(ruta)
                self.assertTrue(resultado.genero_asm, [str(e) for e in resultado.errores])
                self.assertEqual(resultado.ensamblador.pendientes, [])
                self.assertIsNone(resultado.ejecucion.error)

    @unittest.skipUnless(MARS_JAR, "requiere MARS_JAR y Java")
    def test_mars_coincide_con_la_salida_esperada(self):
        for ruta in EJEMPLOS:
            with self.subTest(ejemplo=os.path.basename(ruta)):
                resultado = compilar_ejemplo(ruta)
                esperada = "\n".join(resultado.ejecucion.salida)
                self.assertEqual(ejecutar_en_mars(resultado.ensamblador.asm), esperada)
                self.assertEqual(
                    ejecutar_en_mars(resultado.ensamblador.asm_sin_optimizar), esperada)


if __name__ == "__main__":
    unittest.main()
