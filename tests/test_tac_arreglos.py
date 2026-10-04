"""
Tests de la generación de código intermedio para arreglos:
literales, lectura y escritura por índice, matrices y reciclaje de
temporales en esas expresiones.

Cada programa se analiza con la pipeline completa y se compara el
TAC generado con una salida esperada línea por línea. Los esquemas
están en docs/DISENO_TAC.md §2 (Arreglos).

Corre con: python -m unittest discover -s tests -v
"""

import os
import sys
import unittest

_BASE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(_BASE, "..", "src", "compiler"))

from pipeline import analizar_codigo


class BaseTACArreglos(unittest.TestCase):
    """Nota de direcciones: un arreglo es una referencia (8 bytes), así que
    la variable que sigue a un arreglo global cae en global+8."""

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


class TestArregloLiteral(BaseTACArreglos):

    def test_literal_de_enteros(self):
        self.assertEqual(self.lineas_tac(
            "let notas: integer[] = [90, 85, 100];"),
            ["t1 = newarray 3",
             "t1[0] = 90",
             "t1[1] = 85",
             "t1[2] = 100",
             "global+0 = t1"])

    def test_literal_vacio(self):
        self.assertEqual(self.lineas_tac(
            "let vacio: integer[] = [];"),
            ["t1 = newarray 0",
             "global+0 = t1"])

    def test_literal_de_strings(self):
        self.assertEqual(self.lineas_tac(
            'let nombres: string[] = ["ana", "luis"];'),
            ["t1 = newarray 2",
             't1[0] = "ana"',
             't1[1] = "luis"',
             "global+0 = t1"])

    def test_elementos_que_son_expresiones(self):
        """El arreglo se pide antes de liberar los elementos: no puede
        reciclar el temporal de un elemento y pisarlo."""
        lineas = self.lineas_tac(
            "let a: integer = 3;\n"
            "let b: integer = 4;\n"
            "let calc: integer[] = [a + b, a * b];")
        self.assertEqual(lineas[2:],
                         ["t1 = global+0 + global+4",
                          "t2 = global+0 * global+4",
                          "t3 = newarray 2",
                          "t3[0] = t1",
                          "t3[1] = t2",
                          "global+8 = t3"])

    def test_matriz_literal(self):
        self.assertEqual(self.lineas_tac(
            "let m: integer[][] = [[1, 2], [3, 4]];"),
            ["t1 = newarray 2",
             "t1[0] = 1",
             "t1[1] = 2",
             "t2 = newarray 2",
             "t2[0] = 3",
             "t2[1] = 4",
             "t3 = newarray 2",
             "t3[0] = t1",
             "t3[1] = t2",
             "global+0 = t3"])


class TestLecturaPorIndice(BaseTACArreglos):

    def test_lectura_con_indice_literal(self):
        self.assertEqual(self.lineas_tac(
            "let notas: integer[] = [1, 2];\n"
            "let primera: integer = notas[0];")[-2:],
            ["t1 = global+0[0]",
             "global+8 = t1"])

    def test_lectura_con_indice_variable(self):
        self.assertEqual(self.lineas_tac(
            "let notas: integer[] = [1, 2];\n"
            "let i: integer = 1;\n"
            "let x: integer = notas[i];")[-3:],
            ["global+8 = 1",
             "t1 = global+0[global+8]",
             "global+12 = t1"])

    def test_indice_expresion_reutiliza_su_temporal(self):
        """t1 = i - 1 se consume en la lectura: el resultado sigue
        siendo t1 (un cuádruplo lee antes de escribir)."""
        lineas = self.lineas_tac(
            "let notas: integer[] = [1, 2, 3];\n"
            "let i: integer = 2;\n"
            "let x: integer = notas[i - 1];")
        self.assertEqual(lineas[-3:],
                         ["t1 = global+8 - 1",
                          "t1 = global+0[t1]",
                          "global+12 = t1"])

    def test_lectura_de_matriz_encadena_indices(self):
        lineas = self.lineas_tac(
            "let m: integer[][] = [[1, 2], [3, 4]];\n"
            "let x: integer = m[1][0];")
        self.assertEqual(lineas[-3:],
                         ["t3 = global+0[1]",
                          "t3 = t3[0]",
                          "global+8 = t3"])

    def test_lectura_en_expresion_aritmetica(self):
        lineas = self.lineas_tac(
            "let notas: integer[] = [1, 2];\n"
            "let s: integer = notas[0] + notas[1];")
        self.assertEqual(lineas[-4:],
                         ["t1 = global+0[0]",
                          "t2 = global+0[1]",
                          "t1 = t1 + t2",
                          "global+8 = t1"])


class TestEscrituraPorIndice(BaseTACArreglos):

    def test_escritura_con_indice_literal(self):
        self.assertEqual(self.lineas_tac(
            "let notas: integer[] = [1, 2];\n"
            "notas[1] = 70;")[-1:],
            ["global+0[1] = 70"])

    def test_escritura_con_indice_variable(self):
        self.assertEqual(self.lineas_tac(
            "let notas: integer[] = [1, 2];\n"
            "let i: integer = 0;\n"
            "notas[i] = 9;")[-1:],
            ["global+0[global+8] = 9"])

    def test_escritura_con_valor_calculado(self):
        """a[i] = a[i-1] + 5: el lado izquierdo se resuelve primero y
        no se lee, solo se escribe al final."""
        lineas = self.lineas_tac(
            "let notas: integer[] = [1, 2, 3];\n"
            "let i: integer = 2;\n"
            "notas[i] = notas[i - 1] + 5;")
        self.assertEqual(lineas[-4:],
                         ["t1 = global+8 - 1",
                          "t1 = global+0[t1]",
                          "t1 = t1 + 5",
                          "global+0[global+8] = t1"])

    def test_escritura_en_matriz_lee_la_fila_y_escribe_la_celda(self):
        lineas = self.lineas_tac(
            "let m: integer[][] = [[1, 2], [3, 4]];\n"
            "m[0][1] = 7;")
        self.assertEqual(lineas[-2:],
                         ["t3 = global+0[0]",
                          "t3[1] = 7"])

    def test_indice_con_expresion_vive_hasta_la_escritura(self):
        """El temporal del índice está vivo mientras se evalúa el valor:
        el valor no puede reciclarlo."""
        lineas = self.lineas_tac(
            "let notas: integer[] = [1, 2, 3];\n"
            "let i: integer = 0;\n"
            "let j: integer = 1;\n"
            "notas[i + 1] = j * 2;")
        self.assertEqual(lineas[-3:],
                         ["t1 = global+8 + 1",
                          "t2 = global+12 * 2",
                          "global+0[t1] = t2"])


class TestArreglosEnFunciones(BaseTACArreglos):

    def test_arreglo_local_usa_direccion_de_marco(self):
        lineas = self.lineas_tac(
            "function primero(): integer {\n"
            "  let xs: integer[] = [7, 8];\n"
            "  return xs[0];\n"
            "}")
        self.assertEqual(lineas,
                         ["function primero:",
                          "t1 = newarray 2",
                          "t1[0] = 7",
                          "t1[1] = 8",
                          "fp+16 = t1",
                          "t1 = fp+16[0]",
                          "return t1",
                          "endfunction primero"])

    def test_arreglo_como_argumento(self):
        lineas = self.lineas_tac(
            "function suma(xs: integer[]): integer { return xs[0]; }\n"
            "let notas: integer[] = [1, 2];\n"
            "let r: integer = suma(notas);")
        self.assertIn("param global+0", lineas)
        self.assertIn("t1 = call suma, 1", lineas)


class TestArreglosYReciclaje(BaseTACArreglos):

    def test_no_quedan_temporales_vivos(self):
        resultado = self.analizar(
            "let m: integer[][] = [[1, 2], [3, 4]];\n"
            "let x: integer = m[1][0];\n"
            "m[0][1] = x + 1;")
        self.assertEqual(resultado.temporales["vivos_al_final"], 0)

    def test_hay_reutilizacion(self):
        resultado = self.analizar(
            "let notas: integer[] = [1, 2, 3];\n"
            "let a: integer = notas[0];\n"
            "let b: integer = notas[1];\n"
            "let c: integer = notas[2];")
        self.assertGreater(resultado.temporales["reutilizaciones"], 0)


class TestCompuertaConArreglos(unittest.TestCase):

    def test_error_semantico_en_arreglo_no_genera_tac(self):
        r = analizar_codigo(
            "test.cps",
            'let notas: integer[] = [1, 2];\nlet x: integer = notas["a"];')
        self.assertFalse(r.es_valido)
        self.assertFalse(r.genero_tac)
        self.assertEqual(r.tac_texto, "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
