"""
Tests de las reglas puras del sistema de tipos.
Corre con: python -m pytest tests/test_type_system.py -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "semantic"))

import type_system as ts


class TestOperacionesAritmeticas(unittest.TestCase):

    def test_suma_de_enteros_es_entero(self):
        self.assertEqual(ts.arithmetic("+", ts.INTEGER, ts.INTEGER), ts.INTEGER)

    def test_suma_de_floats_es_float(self):
        self.assertEqual(ts.arithmetic("+", ts.FLOAT, ts.FLOAT), ts.FLOAT)

    def test_operaciones_mixtas_entero_y_float_generan_float(self):
        for op in ("+", "-", "*", "/"):
            self.assertEqual(ts.arithmetic(op, ts.INTEGER, ts.FLOAT), ts.FLOAT)
            self.assertEqual(ts.arithmetic(op, ts.FLOAT, ts.INTEGER), ts.FLOAT)

    def test_entero_es_asignable_a_float_pero_no_al_reves(self):
        self.assertTrue(ts.assignable(ts.FLOAT, ts.INTEGER))
        self.assertFalse(ts.assignable(ts.INTEGER, ts.FLOAT))

    def test_comparacion_entre_float_e_integer_es_valida(self):
        for op in ("==", "!=", "<", "<=", ">", ">="):
            self.assertEqual(
                ts.comparison(op, ts.FLOAT, ts.INTEGER), ts.BOOLEAN)
            self.assertEqual(
                ts.comparison(op, ts.INTEGER, ts.FLOAT), ts.BOOLEAN)

    def test_resta_multiplicacion_division_y_modulo_de_enteros(self):
        for op in ("-", "*", "/", "%"):
            self.assertEqual(ts.arithmetic(op, ts.INTEGER, ts.INTEGER), ts.INTEGER)

    def test_suma_de_strings_concatena(self):
        self.assertEqual(ts.arithmetic("+", ts.STRING, ts.STRING), ts.STRING)

    def test_resta_de_strings_es_invalida(self):
        self.assertIsNone(ts.arithmetic("-", ts.STRING, ts.STRING))

    def test_suma_de_entero_con_string_es_invalida(self):
        self.assertIsNone(ts.arithmetic("+", ts.INTEGER, ts.STRING))

    def test_suma_con_boolean_es_invalida(self):
        self.assertIsNone(ts.arithmetic("+", ts.BOOLEAN, ts.INTEGER))


class TestOperacionesLogicas(unittest.TestCase):

    def test_and_y_or_entre_booleans(self):
        self.assertEqual(ts.logical("&&", ts.BOOLEAN, ts.BOOLEAN), ts.BOOLEAN)
        self.assertEqual(ts.logical("||", ts.BOOLEAN, ts.BOOLEAN), ts.BOOLEAN)

    def test_and_con_entero_es_invalido(self):
        self.assertIsNone(ts.logical("&&", ts.INTEGER, ts.BOOLEAN))

    def test_negacion_de_boolean(self):
        self.assertEqual(ts.unary("!", ts.BOOLEAN), ts.BOOLEAN)

    def test_negacion_de_string_es_invalida(self):
        self.assertIsNone(ts.unary("!", ts.STRING))

    def test_menos_unario_solo_sobre_numericos(self):
        self.assertEqual(ts.unary("-", ts.INTEGER), ts.INTEGER)
        self.assertIsNone(ts.unary("-", ts.BOOLEAN))


class TestComparaciones(unittest.TestCase):

    def test_igualdad_entre_mismo_tipo(self):
        self.assertEqual(ts.comparison("==", ts.STRING, ts.STRING), ts.BOOLEAN)

    def test_igualdad_entre_tipos_distintos_es_invalida(self):
        self.assertIsNone(ts.comparison("==", ts.STRING, ts.INTEGER))

    def test_relacionales_entre_numericos(self):
        for op in ("<", "<=", ">", ">="):
            self.assertEqual(ts.comparison(op, ts.INTEGER, ts.INTEGER), ts.BOOLEAN)

    def test_relacionales_entre_strings_son_invalidas(self):
        self.assertIsNone(ts.comparison("<", ts.STRING, ts.STRING))

    def test_comparar_clase_con_null_es_valido(self):
        self.assertEqual(ts.comparison("==", "Perro", ts.NULL), ts.BOOLEAN)

    def test_comparar_entero_con_null_es_invalido(self):
        self.assertIsNone(ts.comparison("==", ts.INTEGER, ts.NULL))


class TestAsignabilidad(unittest.TestCase):

    def test_mismo_tipo_es_asignable(self):
        self.assertTrue(ts.assignable(ts.INTEGER, ts.INTEGER))

    def test_tipo_distinto_no_es_asignable(self):
        self.assertFalse(ts.assignable(ts.INTEGER, ts.BOOLEAN))

    def test_null_a_clase_y_arreglo_es_asignable(self):
        self.assertTrue(ts.assignable("Perro", ts.NULL))
        self.assertTrue(ts.assignable("integer[]", ts.NULL))

    def test_null_a_primitivo_no_es_asignable(self):
        self.assertFalse(ts.assignable(ts.INTEGER, ts.NULL))

    def test_arreglos_del_mismo_tipo_de_elemento(self):
        self.assertTrue(ts.assignable("integer[]", "integer[]"))
        self.assertFalse(ts.assignable("integer[]", "string[]"))

    def test_arreglo_vacio_es_asignable_a_cualquier_arreglo(self):
        self.assertTrue(ts.assignable("string[]", "null[]"))

    def test_subclase_es_asignable_a_su_clase_padre_con_el_hook(self):
        jerarquia = {"Perro": "Animal"}
        es_subclase = lambda hijo, padre: jerarquia.get(hijo) == padre
        self.assertTrue(ts.assignable("Animal", "Perro", es_subclase))
        self.assertFalse(ts.assignable("Perro", "Animal", es_subclase))


class TestPropagacionDelTipoError(unittest.TestCase):
    """Un tipo ya erróneo no debe generar errores derivados."""

    def test_operaciones_con_error_devuelven_error(self):
        self.assertEqual(ts.arithmetic("+", ts.ERROR, ts.INTEGER), ts.ERROR)
        self.assertEqual(ts.logical("&&", ts.ERROR, ts.BOOLEAN), ts.ERROR)
        self.assertEqual(ts.comparison("<", ts.ERROR, ts.INTEGER), ts.ERROR)
        self.assertEqual(ts.unary("!", ts.ERROR), ts.ERROR)

    def test_asignar_desde_o_hacia_error_no_se_reporta(self):
        self.assertTrue(ts.assignable(ts.ERROR, ts.STRING))
        self.assertTrue(ts.assignable(ts.INTEGER, ts.ERROR))


class TestArreglos(unittest.TestCase):

    def test_utilidades_de_arreglo(self):
        self.assertTrue(ts.is_array("integer[]"))
        self.assertEqual(ts.element_type("integer[][]"), "integer[]")
        self.assertEqual(ts.array_of(ts.STRING), "string[]")

    def test_unificar_elementos_del_mismo_tipo(self):
        self.assertEqual(ts.unify([ts.INTEGER, ts.INTEGER]), ts.INTEGER)

    def test_unificar_elementos_incompatibles(self):
        self.assertIsNone(ts.unify([ts.INTEGER, ts.STRING]))

    def test_unificar_arreglo_vacio(self):
        self.assertEqual(ts.unify([]), ts.NULL)


if __name__ == "__main__":
    unittest.main(verbosity=2)
