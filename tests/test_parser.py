"""
Batería de tests de la infraestructura de la Persona 3: analizador léxico,
analizador sintáctico (ANTLR) y pipeline unificado que los junta.

Corre con: python -m unittest discover -s tests -v
"""

import os
import sys
import unittest

_AQUI = os.path.dirname(__file__)
_PROYECTO = os.path.dirname(_AQUI)
for _carpeta in ("src/parser", "src/lexico", "src/compiler"):
    sys.path.insert(0, os.path.join(_PROYECTO, _carpeta))

import parse as sintactico
import analizador as lexico
from pipeline import analizar_codigo


CODIGO_VALIDO = """
const MAX: integer = 10;

let numeros: integer[] = [1, 2, 3];

function suma(n: integer): integer {
  let total: integer = 0;
  total = total + n;
  return total;
}

print(suma(MAX));
"""


class TestLexico(unittest.TestCase):

    def test_codigo_valido_no_reporta_errores(self):
        r = lexico.analizar_texto(CODIGO_VALIDO)
        self.assertTrue(r.es_valido)
        self.assertGreater(len(r.tokens), 0)

    def test_caracter_invalido_se_reporta(self):
        r = lexico.analizar_texto("let x: integer = 5 ¿;")
        self.assertFalse(r.es_valido)
        self.assertEqual(r.errores[0].tipo, "Léxico")
        self.assertNotEqual(r.errores[0].descripcion, "")

    def test_tokens_tienen_linea_y_columna(self):
        r = lexico.analizar_texto("let x: integer;")
        for t in r.tokens:
            self.assertGreaterEqual(t.linea, 1)
            self.assertGreaterEqual(t.columna, 1)
            self.assertNotEqual(t.lexema, "")


class TestSintactico(unittest.TestCase):

    def test_codigo_valido_no_reporta_errores(self):
        r = sintactico.analizar_texto(CODIGO_VALIDO)
        self.assertTrue(r.es_valido)
        self.assertIsNotNone(r.arbol)

    def test_arbol_en_texto_y_estructura(self):
        r = sintactico.analizar_texto(CODIGO_VALIDO)
        self.assertTrue(sintactico.arbol_a_texto(r.arbol).startswith("(program"))
        raiz = sintactico.arbol_a_estructura(r.arbol)
        self.assertEqual(raiz[0], "program")
        self.assertIsInstance(raiz, list)

    def test_error_sintactico_se_reporta_con_posicion(self):
        r = sintactico.analizar_texto("let x: integer = 10")
        self.assertFalse(r.es_valido)
        e = r.errores[0]
        self.assertEqual(e.tipo, "Sintáctico")
        self.assertGreaterEqual(e.linea, 1)
        self.assertIn("se esperaba", e.descripcion)

    def test_se_acumulan_varios_errores(self):
        r = sintactico.analizar_texto(
            "function f() { return ;\nfunction g() { return ;"
        )
        self.assertGreater(len(r.errores), 0)

    def test_arbol_vacio_si_no_hay_arbol(self):
        self.assertEqual(sintactico.arbol_a_texto(None), "")
        self.assertEqual(sintactico.arbol_a_estructura(None), [])


class TestPipeline(unittest.TestCase):

    def test_valido_sin_errores(self):
        r = analizar_codigo("ok.cps", CODIGO_VALIDO)
        self.assertTrue(r.es_valido)
        self.assertEqual(r.errores, [])
        self.assertGreater(len(r.tokens), 0)
        self.assertTrue(r.arbol.startswith("(program"))
        self.assertEqual(r.arbol_estructura[0], "program")

    def test_junta_errores_lexicos_y_sintacticos_ordenados(self):
        r = analizar_codigo("mixto.cps", "let x: integer = ¿;\nfunction f( {")
        self.assertFalse(r.es_valido)
        tipos = {e.tipo for e in r.errores}
        self.assertIn("Léxico", tipos)
        self.assertIn("Sintáctico", tipos)
        filas = [(e.linea, e.columna) for e in r.errores]
        self.assertEqual(filas, sorted(filas))

    def test_ok_semantica_del_repo_es_valido(self):
        ruta = os.path.join(_PROYECTO, "ejemplos", "ok_semantica.cps")
        with open(ruta, encoding="utf-8") as f:
            r = analizar_codigo("ok_semantica.cps", f.read())
        self.assertTrue(r.es_valido, [str(e) for e in r.errores])
        self.assertGreater(len(r.tokens), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)