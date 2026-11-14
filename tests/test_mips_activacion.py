"""
Tests del árbol de activación (intérprete del TAC): forma del árbol con
recursividad, funciones anidadas y métodos, salida esperada, excepciones y
límites de ejecución.

Corre con: python -m unittest discover -s tests -v
"""

import os
import sys
import unittest

_BASE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(_BASE, "..", "src", "compiler"))
sys.path.insert(0, os.path.join(_BASE, "..", "src", "backend"))

from pipeline import analizar_codigo
from backend import generar_ensamblador
from activacion import construir_arbol, formatear

RUTA_EJEMPLOS = os.path.join(_BASE, "..", "ejemplos")


def ejecutar(codigo):
    resultado = analizar_codigo("test.cps", codigo)
    assert resultado.genero_tac, [str(e) for e in resultado.errores]
    backend = generar_ensamblador(resultado.tac, resultado.tabla, resultado.memoria)
    return construir_arbol(resultado.tac, resultado.tabla, resultado.memoria, backend.marcos)


def ejecutar_ejemplo(nombre):
    with open(os.path.join(RUTA_EJEMPLOS, nombre), encoding="utf-8") as fh:
        return ejecutar(fh.read())


class TestArbol(unittest.TestCase):

    def test_programa_sin_llamadas_solo_tiene_main(self):
        arbol = ejecutar("let a: integer = 1; print(a);")
        self.assertEqual(arbol.raiz.etiqueta(), "main")
        self.assertEqual(arbol.raiz.hijos, [])
        self.assertEqual(arbol.salida, ["1"])

    def test_recursion_lineal(self):
        arbol = ejecutar_ejemplo("tac_06_recursividad.cps")
        factorial = arbol.raiz.hijos[0]
        self.assertEqual(factorial.etiqueta(), "factorial(5) → 120")
        profundidad, nodo = 0, factorial
        while nodo.hijos:
            nodo = nodo.hijos[0]
            profundidad += 1
        self.assertEqual(profundidad, 4)            # factorial(1) es la hoja
        self.assertEqual(nodo.etiqueta(), "factorial(1) → 1")

    def test_recursion_en_arbol(self):
        arbol = ejecutar_ejemplo("tac_06_recursividad.cps")
        fibonacci = arbol.raiz.hijos[1]
        self.assertEqual(len(fibonacci.hijos), 2)   # fib(5) y fib(4)
        total = sum(1 for n in arbol.nodos() if n.funcion == "fibonacci")
        self.assertEqual(total, 25)                 # llamadas de fib(6)

    def test_cada_activacion_tiene_su_marco(self):
        arbol = ejecutar_ejemplo("tac_06_recursividad.cps")
        tamanos = {n.tamano_marco for n in arbol.nodos() if n.funcion == "factorial"}
        self.assertEqual(len(tamanos), 1)
        self.assertGreater(tamanos.pop(), 0)

    def test_funcion_anidada_lee_la_variable_capturada(self):
        arbol = ejecutar_ejemplo("tac_05_funciones.cps")
        contador = [n for n in arbol.raiz.hijos if n.funcion == "contador"][0]
        self.assertEqual(contador.hijos[0].etiqueta(), "contador.interno(5) → 15")

    def test_metodos_no_muestran_el_receptor(self):
        arbol = ejecutar_ejemplo("tac_08_herencia.cps")
        etiquetas = [n.etiqueta() for n in arbol.raiz.hijos]
        self.assertIn('Animal.constructor("Toby")', etiquetas)
        self.assertEqual(arbol.salida, ["Toby ladra", "Soy Toby", "Toby ladra y juega"])

    def test_profundidad_maxima(self):
        arbol = ejecutar_ejemplo("tac_06_recursividad.cps")
        self.assertEqual(arbol.profundidad_maxima, 6)   # main + fib(6)…fib(1)

    def test_texto_y_dot(self):
        arbol = ejecutar_ejemplo("tac_06_recursividad.cps")
        self.assertIn("└── factorial(1) → 1", arbol.como_texto())
        dot = arbol.como_dot()
        self.assertTrue(dot.startswith("digraph"))
        self.assertIn("n0 -> n1", dot)


class TestSalida(unittest.TestCase):

    def test_aritmetica_de_32_bits(self):
        arbol = ejecutar("print(-17 / 5); print(-17 % 5); print(2147483647 + 1);")
        self.assertEqual(arbol.salida, ["-3", "-2", "-2147483648"])

    def test_float_como_mars(self):
        arbol = ejecutar("let x: float = 2.5; print(x * 4 + 1.5); let y: float = 3; print(y);")
        self.assertEqual(arbol.salida, ["11.5", "3.0"])

    def test_formatear(self):
        self.assertEqual(formatear(True), "true")
        self.assertEqual(formatear(None), "null")
        self.assertEqual(formatear(0.1), "0.1")

    def test_excepcion_atrapada_por_catch(self):
        arbol = ejecutar_ejemplo("tac_07_trycatch.cps")
        self.assertIsNone(arbol.error)
        self.assertEqual(arbol.salida, ["Error atrapado", "-1"])

    def test_excepcion_no_atrapada(self):
        arbol = ejecutar("let a: integer[] = [1]; print(a[3]);")
        self.assertIn("fuera de rango", arbol.error)


class TestLimites(unittest.TestCase):

    def test_ciclo_infinito_se_corta(self):
        arbol = ejecutar("let i: integer = 0; while (i >= 0) { i = i + 1; }")
        self.assertIn("instrucciones", arbol.error)

    def test_recursion_sin_caso_base_se_corta(self):
        arbol = ejecutar("""
        function f(n: integer): integer { return f(n + 1); }
        print(f(0));
        """)
        self.assertIn("activaciones anidadas", arbol.error)

    def test_nodos_dibujados_tienen_tope(self):
        arbol = ejecutar("""
        function fib(n: integer): integer {
          if (n < 2) { return n; }
          return fib(n - 1) + fib(n - 2);
        }
        print(fib(15));
        """)
        self.assertEqual(arbol.salida, ["610"])
        self.assertGreater(arbol.nodos_omitidos, 0)
        self.assertIn("activación(es) más", arbol.como_texto())


if __name__ == "__main__":
    unittest.main()
