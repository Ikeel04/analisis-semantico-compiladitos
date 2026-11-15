"""
Tests del backend de control de flujo y try/catch: saltos y etiquetas
(`label`/`goto`/`if`/`ifFalse`, `break`/`continue`) y manejo de excepciones
con `__lanzar` (parte 2).

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

from test_mips_traductor import MARS_JAR, compilar, ejecutar_en_mars


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


class TestTryCatch(unittest.TestCase):
    """Parte 2: try/catch en el backend MIPS — pila de frames, rutinas de error
    y `__lanzar`."""

    CODIGO_TRY_DIVISION_POR_CERO = """
        let a: integer = 10;
        let b: integer = 0;
        let resultado: integer = 0;
        try { resultado = a / b; } catch (err) { resultado = -1; print("Error atrapado"); }
        print(resultado);
        """

    def test_intento_apila_frame_y_salta_a_catch(self):
        resultado = compilar(self.CODIGO_TRY_DIVISION_POR_CERO)
        self.assertEqual(resultado.pendientes, [])
        # Pila de try: marco de 12 bytes (catch, $fp, $sp) con label alineado.
        self.assertIn("__pila_try: .space 96", resultado.asm)
        self.assertIn("        .align 4", resultado.asm)
        # Antes de dividir: si el divisor es cero, saltar a la rutina de error.
        self.assertIn("beqz", resultado.asm)
        self.assertIn("__error_division", resultado.asm)
        # `__lanzar` restaura el frame y salta al catch con `jr`.
        self.assertIn("__lanzar", resultado.asm)
        self.assertIn("jr", resultado.asm)

    @unittest.skipUnless(MARS_JAR, "requiere MARS_JAR y Java")
    def test_mars_catch_de_division_por_cero(self):
        """Con el catch: la división por cero salta a `__lanzar`, que restaura el
        frame y salta al catch; el programa continúa con el valor de catch."""
        self.assertEqual(ejecutar_en_mars(compilar(self.CODIGO_TRY_DIVISION_POR_CERO).asm),
                         "Error atrapado\n-1")


if __name__ == "__main__":
    unittest.main()
