"""
Tests del backend de control de flujo: saltos y etiquetas (parte 2).

Verifica que los manejadores de `label`, `goto`, `if` y `ifFalse` que registra
`src/backend/control.py` se traduzcan al MIPS esperado (`j`, `beqz`, `bnez` y
etiquetas) y que ningún cuádruplo de control quede sin manejador.

Los tests que ejecutan MARS necesitan MARS_JAR (ver test_mips_traductor.py).

Corre con: python -m unittest discover -s tests -v
"""

import os
import sys
import unittest

_BASE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(_BASE, "..", "src", "compiler"))
sys.path.insert(0, os.path.join(_BASE, "..", "src", "backend"))

from test_mips_traductor import compilar


class TestFlujoControl(unittest.TestCase):

    def test_if_no_genera_pendientes(self):
        resultado = compilar("let n: integer = 3; if (n > 2) { print(n); }")
        self.assertIsNotNone(resultado.pendientes)
        self.assertEqual(resultado.pendientes, [])
        # ifFalse: la condición es falsa -> salta al fin.
        self.assertIn("beqz", resultado.asm)
        self.assertIn("L1_if_fin:", resultado.asm)

    def test_if_else(self):
        resultado = compilar("""
            let n: integer = 3;
            let total: integer = 0;
            if (n > 2) { total = total + 1; } else { total = total - 1; }
            """)
        self.assertEqual(resultado.pendientes, [])
        self.assertIn("beqz", resultado.asm)     # condición falsa -> else
        self.assertIn("j       L2_if_fin", resultado.asm)  # goto fin del if
        self.assertIn("L2_if_fin:", resultado.asm)

    def test_while(self):
        resultado = compilar("""
            let n: integer = 3;
            while (n > 0) { n = n - 1; }
            """)
        self.assertEqual(resultado.pendientes, [])
        self.assertIn("beqz", resultado.asm)     # condición falsa -> fin
        self.assertIn("j       L1_while_inicio", resultado.asm)  # goto al inicio
        self.assertIn("L2_while_fin:", resultado.asm)

    def test_do_while(self):
        resultado = compilar("""
            let total: integer = 0;
            do { total = total + 1; } while (total < 5);
            """)
        self.assertEqual(resultado.pendientes, [])
        self.assertIn("bnez", resultado.asm)     # condición verdadera -> repetir
        self.assertIn("L1_dowhile_inicio:", resultado.asm)


if __name__ == "__main__":
    unittest.main()
