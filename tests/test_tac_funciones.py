"""
Tests de la generación de código intermedio para llamadas
a funciones: parámetros, call, recursión, funciones y
métodos anidados.

Cada programa se analiza con la pipeline completa y se
compara el TAC generado con una salida esperada línea por
línea. Los esquemas que debe producir están en
docs/DISEÑO_TAC.md §2.

Corre con: python -m unittest discover -s tests -v
"""

import os
import sys
import unittest

_BASE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(_BASE, "..", "src", "compiler"))

from pipeline import analizar_codigo


class BaseTACFunciones(unittest.TestCase):

    def analizar(self, codigo):
        resultado = analizar_codigo("test.cps", codigo)
        self.assertTrue(resultado.es_valido,
                        [str(e) for e in resultado.errores])
        self.assertTrue(resultado.genero_tac)
        return resultado

    def lineas_tac(self, codigo):
        return [linea.strip()
                for linea in self.analizar(codigo)
                .tac.como_texto().splitlines()]


class TestLlamadas(BaseTACFunciones):

    def test_llamada_con_retorno(self):
        self.assertEqual(self.lineas_tac(
            "function suma(a: integer, b: integer): integer {\n"
            "  return a + b;\n"
            "}\n"
            "let x: integer = suma(1, 2);\n"),
            ["function suma:",
             "t1 = fp+16 + fp+20",
             "return t1",
             "endfunction suma",
             "param 1",
             "param 2",
             "t1 = call suma, 2",
             "global+0 = t1"])

    def test_llamada_void_sin_resultado(self):
        self.assertEqual(self.lineas_tac(
            "function saludar(): void {\n"
            '  print("hola");\n'
            "}\n"
            "saludar();\n"),
            ["function saludar:",
             'print "hola"',
             "endfunction saludar",
             "call saludar, 0"])

    def test_argumentos_son_expresiones(self):
        self.assertEqual(self.lineas_tac(
            "function f(a: integer): integer {\n"
            "  return a;\n"
            "}\n"
            "let x: integer = f(1 + 2);\n"),
            ["function f:",
             "return fp+16",
             "endfunction f",
             "t1 = 1 + 2",
             "param t1",
             "t2 = call f, 1",
             "global+0 = t2"])

    def test_llamada_como_argumento(self):
        """El resultado de la llamada interna es un
        temporal que vive hasta el call externo."""
        self.assertEqual(self.lineas_tac(
            "function f(a: integer): integer {\n"
            "  return a;\n"
            "}\n"
            "let x: integer = f(f(1));\n"),
            ["function f:",
             "return fp+16",
             "endfunction f",
             "param 1",
             "t1 = call f, 1",
             "param t1",
             "t2 = call f, 1",
             "global+0 = t2"])

    def test_reciclaje_de_temporales_de_argumentos(self):
        """Los temporales de los argumentos se liberan
        tras el call: la suma reutiliza ambos."""
        self.assertEqual(self.lineas_tac(
            "function f(a: integer): integer {\n"
            "  return a;\n"
            "}\n"
            "let x: integer = f(1) + f(2);\n"),
            ["function f:",
             "return fp+16",
             "endfunction f",
             "param 1",
             "t1 = call f, 1",
             "param 2",
             "t2 = call f, 1",
             "t1 = t1 + t2",
             "global+0 = t1"])


class TestRecursion(BaseTACFunciones):

    def test_recursion(self):
        """Cada call es independiente: la recursión no
        necesita nada especial (el registro de activación
        es un molde)."""
        self.assertEqual(self.lineas_tac(
            "function factorial(n: integer): integer {\n"
            "  if (n <= 1) {\n"
            "    return 1;\n"
            "  }\n"
            "  return n * factorial(n - 1);\n"
            "}\n"
            "let x: integer = factorial(5);\n"),
            ["function factorial:",
             "t1 = fp+16 <= 1",
             "ifFalse t1 goto L1_if_fin",
             "return 1",
             "L1_if_fin:",
             "t1 = fp+16 - 1",
             "param t1",
             "t2 = call factorial, 1",
             "t2 = fp+16 * t2",
             "return t2",
             "endfunction factorial",
             "param 5",
             "t1 = call factorial, 1",
             "global+0 = t1"])


class TestNombresCualificados(BaseTACFunciones):

    def test_funcion_anidada(self):
        """El call usa el nombre del ámbito que declaró
        la función, no el del sitio de llamada."""
        self.assertEqual(self.lineas_tac(
            "function contador(): integer {\n"
            "  function interno(): integer {\n"
            "    return 1;\n"
            "  }\n"
            "  return interno();\n"
            "}\n"
            "let x: integer = contador();\n"),
            ["function contador:",
             "function contador.interno:",
             "return 1",
             "endfunction contador.interno",
             "t1 = call contador.interno, 0",
             "return t1",
             "endfunction contador",
             "t1 = call contador, 0",
             "global+0 = t1"])

    def test_metodo_se_resuelve_con_su_clase(self):
        """Un método llamado por su nombre dentro de su clase tiene receptor
        implícito: 'this' va como primer param y el N del call lo cuenta."""
        self.assertEqual(self.lineas_tac(
            "class Pila {\n"
            "  function tamano(): integer {\n"
            "    return 0;\n"
            "  }\n"
            "  function doble(): integer {\n"
            "    return tamano() * 2;\n"
            "  }\n"
            "}\n"),
            ["function Pila.tamano:",
             "return 0",
             "endfunction Pila.tamano",
             "function Pila.doble:",
             "param this",
             "t1 = call Pila.tamano, 1",
             "t1 = t1 * 2",
             "return t1",
             "endfunction Pila.doble"])

    def test_toda_llamada_tiene_su_funcion(self):
        """Todo 'call' refiere a una función declarada,
        con su nombre cualificado."""
        resultado = self.analizar(
            "function f(a: integer): integer {\n"
            "  return a;\n"
            "}\n"
            "function g(a: integer): integer {\n"
            "  return f(a);\n"
            "}\n"
            "class C {\n"
            "  function m(): integer {\n"
            "    return g(1);\n"
            "  }\n"
            "}\n"
            "let x: integer = g(2);\n")
        funciones = {c.arg1 for c in resultado.tac
                     if c.op == "function"}
        llamadas = {c.arg1 for c in resultado.tac
                    if c.op == "call"}
        self.assertEqual(llamadas - funciones, set())


if __name__ == "__main__":
    unittest.main()