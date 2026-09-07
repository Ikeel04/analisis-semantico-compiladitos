"""
Tests de las reglas semánticas de clases, objetos e índices de arreglos.
Cada regla tiene su caso exitoso y su caso fallido.

Corre con: python -m unittest discover -s tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "semantic"))

import type_system as ts
from checker import SemanticChecker


class BaseChecker(unittest.TestCase):

    def setUp(self):
        self.c = SemanticChecker()

    def assertSinErrores(self):
        self.assertEqual(len(self.c.errors), 0, self.c.errors.as_text())

    def assertErrores(self, cantidad):
        self.assertEqual(len(self.c.errors), cantidad, self.c.errors.as_text())

    def assertMensaje(self, fragmento):
        self.assertIn(fragmento, self.c.errors.as_text())

    def crear_clase(self, nombre, parent=None):
        """Declara la clase en el ámbito global y regresa al global."""
        simbolo = self.c.declare_class(nombre, parent=parent)
        self.c.enter_class(simbolo)
        self.c.exit_class()
        return simbolo


class TestDeclaracionDeClases(BaseChecker):

    def test_clase_simple_sin_errores(self):
        self.crear_clase("Punto")
        self.assertSinErrores()

    def test_clase_con_superclase_declarada(self):
        self.crear_clase("Figura")
        self.crear_clase("Cuadrado", parent="Figura")
        self.assertSinErrores()

    def test_superclase_inexistente_reporta_y_la_ignora(self):
        self.crear_clase("Cuadrado", parent="Circulo")
        self.assertErrores(1)
        self.assertMensaje("la clase 'Circulo' no ha sido declarada")

    def test_clase_redeclarada_en_el_mismo_ambito(self):
        self.c.declare_class("Punto")
        self.c.declare_class("Punto")
        self.assertMensaje("'Punto' ya fue declarado en este ámbito")


class TestHerencia(BaseChecker):

    def setUp(self):
        super().setUp()
        self.crear_clase("Animal")
        self.crear_clase("Mamifero", parent="Animal")
        self.crear_clase("Perro", parent="Mamifero")

    def test_subclase_directa_e_indirecta(self):
        self.assertTrue(self.c.is_subclass("Perro", "Mamifero"))
        self.assertTrue(self.c.is_subclass("Perro", "Animal"))
        self.assertTrue(self.c.is_subclass("Mamifero", "Animal"))
        self.assertFalse(self.c.is_subclass("Animal", "Perro"))

    def test_clase_es_subclase_de_si_misma(self):
        self.assertTrue(self.c.is_subclass("Perro", "Perro"))

    def test_subclase_se_puede_asignar_a_la_base(self):
        self.assertTrue(self.c.check_compatible("Animal", "Perro", "prueba"))

    def test_comparacion_entre_base_y_subclase(self):
        self.assertEqual(self.c.comparison("==", "Animal", "Perro"), ts.BOOLEAN)
        self.assertSinErrores()


class TestMiembros(BaseChecker):

    def setUp(self):
        super().setUp()
        self.c.declare_class("Rectangulo")
        rect = self.c.table.lookup_local("Rectangulo")
        self.c.enter_class(rect)
        self.c.declare_variable("ancho", ts.INTEGER, ts.INTEGER)
        self.c.declare_constant("NOMBRE", ts.STRING, ts.STRING)
        self.c.declare_function("area", [])
        self.c.declare_function("duplicado", [], ts.INTEGER)
        self.c.exit_class()

    def test_acceso_a_atributo_devuelve_su_tipo(self):
        self.assertEqual(self.c.check_member_access("Rectangulo", "ancho"), ts.INTEGER)
        self.assertSinErrores()

    def test_acceso_a_miembro_inexistente(self):
        self.assertEqual(self.c.check_member_access("Rectangulo", "lado"), ts.ERROR)
        self.assertMensaje("no tiene un miembro llamado 'lado'")

    def test_acceso_a_metodo_sin_parentesis(self):
        self.assertEqual(self.c.check_member_access("Rectangulo", "area"), ts.ERROR)
        self.assertMensaje("llámalo con paréntesis")

    def test_acceso_a_miembro_de_tipo_no_clase(self):
        self.assertEqual(self.c.check_member_access(ts.INTEGER, "ancho"), ts.ERROR)
        self.assertMensaje("no es una clase")

    def test_llamada_a_metodo_correcta(self):
        self.assertEqual(self.c.check_member_call("Rectangulo", "duplicado", []), ts.INTEGER)
        self.assertSinErrores()

    def test_llamada_a_metodo_con_argumentos_incorrectos(self):
        self.c.check_member_call("Rectangulo", "area", [ts.INTEGER])
        self.assertMensaje("espera 0 argumento(s)")

    def test_llamada_a_atributo_como_metodo(self):
        self.c.check_member_call("Rectangulo", "ancho", [])
        self.assertMensaje("'ancho' no es un método")

    def test_llamada_a_metodo_de_tipo_no_clase(self):
        self.assertEqual(self.c.check_member_call(ts.INTEGER, "area", []), ts.ERROR)
        self.assertMensaje("no es una clase")

    def test_asignacion_a_atributo_valida(self):
        self.assertEqual(self.c.check_property_assign("Rectangulo", "ancho", ts.INTEGER),
                         ts.INTEGER)
        self.assertSinErrores()

    def test_asignacion_a_atributo_con_tipo_incorrecto(self):
        self.assertEqual(self.c.check_property_assign("Rectangulo", "ancho", ts.STRING),
                         ts.ERROR)
        self.assertMensaje("no se puede asignar a 'Rectangulo.ancho'")

    def test_asignacion_a_constante(self):
        self.c.check_property_assign("Rectangulo", "NOMBRE", ts.STRING)
        self.assertMensaje("no se puede reasignar la constante 'NOMBRE'")

    def test_asignacion_a_metodo(self):
        self.c.check_property_assign("Rectangulo", "area", ts.INTEGER)
        self.assertMensaje("no puede asignarse")

    def test_asignacion_a_miembro_inexistente(self):
        self.c.check_property_assign("Rectangulo", "lado", ts.INTEGER)
        self.assertMensaje("no tiene un miembro llamado 'lado'")

    def test_asignacion_a_un_objeto_que_no_es_clase(self):
        self.c.check_property_assign(ts.INTEGER, "ancho", ts.INTEGER)
        self.assertMensaje("no es una clase")

    def test_atributo_sin_tipo_infiere_en_la_primera_asignacion(self):
        self.c.declare_class("Caja")
        caja = self.c.table.lookup_local("Caja")
        self.c.enter_class(caja)
        self.c.declare_variable("contenido")
        self.c.exit_class()
        self.assertEqual(self.c.check_property_assign("Caja", "contenido", ts.STRING),
                         ts.STRING)
        self.assertEqual(self.c.check_member_access("Caja", "contenido"), ts.STRING)
        self.assertSinErrores()


class TestHerenciaDeMiembros(BaseChecker):

    def setUp(self):
        super().setUp()
        self.c.declare_class("Base")
        base = self.c.table.lookup_local("Base")
        self.c.enter_class(base)
        self.c.declare_variable("origen", ts.INTEGER, ts.INTEGER)
        self.c.declare_function("generar", [], ts.INTEGER)
        self.c.declare_function("constructor", [("n", ts.INTEGER)])
        self.c.exit_class()

    def test_miembro_heredado_se_resuelve_en_la_subclase(self):
        self.crear_clase("Hija", parent="Base")
        self.assertEqual(self.c.check_member_access("Hija", "origen"), ts.INTEGER)
        self.assertEqual(self.c.check_member_call("Hija", "generar", []), ts.INTEGER)
        self.assertSinErrores()

    def test_constructor_heredado_valida_argumentos(self):
        self.crear_clase("Hija", parent="Base")
        self.assertEqual(self.c.check_new("Hija", [ts.INTEGER]), "Hija")
        self.assertSinErrores()

    def test_constructor_heredado_rechaza_argumentos_incorrectos(self):
        self.crear_clase("Hija", parent="Base")
        self.c.check_new("Hija", [])
        self.assertMensaje("espera 1 argumento(s)")


class TestConstructorYNew(BaseChecker):

    def test_new_con_constructor_valido_devuelve_la_clase(self):
        self.c.declare_class("Punto")
        p = self.c.table.lookup_local("Punto")
        self.c.enter_class(p)
        self.c.declare_function("constructor", [("x", ts.INTEGER), ("y", ts.INTEGER)])
        self.c.exit_class()
        self.assertEqual(self.c.check_new("Punto", [ts.INTEGER, ts.INTEGER]), "Punto")
        self.assertSinErrores()

    def test_new_con_argumentos_incorrectos(self):
        self.c.declare_class("Punto")
        p = self.c.table.lookup_local("Punto")
        self.c.enter_class(p)
        self.c.declare_function("constructor", [("x", ts.INTEGER)])
        self.c.exit_class()
        self.c.check_new("Punto", [ts.INTEGER, ts.INTEGER])
        self.assertMensaje("'constructor' espera 1 argumento(s) y recibió 2")

    def test_new_de_clase_no_declarada(self):
        self.assertEqual(self.c.check_new("Fantasma", []), ts.ERROR)
        self.assertMensaje("la clase 'Fantasma' no ha sido declarada")

    def test_new_sin_constructor_y_sin_argumentos_queda_valido(self):
        self.c.declare_class("Vacio")
        v = self.c.table.lookup_local("Vacio")
        self.c.enter_class(v)
        self.c.exit_class()
        self.assertEqual(self.c.check_new("Vacio", []), "Vacio")
        self.assertSinErrores()

    def test_new_sin_constructor_con_argumentos(self):
        self.c.declare_class("Vacio")
        v = self.c.table.lookup_local("Vacio")
        self.c.enter_class(v)
        self.c.exit_class()
        self.c.check_new("Vacio", [ts.INTEGER])
        self.assertMensaje("no define un constructor que acepte 1 argumento(s)")

    def test_constructor_no_puede_devolver_tipo(self):
        self.c.declare_class("Punto")
        p = self.c.table.lookup_local("Punto")
        self.c.enter_class(p)
        self.c.declare_function("constructor", [], ts.INTEGER)
        self.assertMensaje("el constructor no puede declarar un tipo de retorno")

    def test_constructor_no_puede_llamarse_directamente(self):
        self.c.declare_class("Punto")
        p = self.c.table.lookup_local("Punto")
        self.c.enter_class(p)
        self.c.declare_function("constructor", [("x", ts.INTEGER)])
        self.c.check_call("constructor", [ts.INTEGER])
        self.assertMensaje("no puede llamarse directamente")


class TestThis(BaseChecker):

    def setUp(self):
        super().setUp()
        self.c.declare_class("Cuenta")
        cuenta = self.c.table.lookup_local("Cuenta")
        self.c.enter_class(cuenta)
        self.c.declare_variable("saldo", ts.INTEGER, ts.INTEGER)
        metodo = self.c.declare_function("depositar", [("monto", ts.INTEGER)])
        self.c.enter_function(metodo)
        self.metodo_abierto = True

    def tearDown(self):
        if getattr(self, "metodo_abierto", False):
            self.c.exit_function()
            self.c.exit_class()

    def test_this_devuelve_el_tipo_de_la_clase_dentro_de_un_metodo(self):
        self.assertEqual(self.c.check_this(), "Cuenta")
        self.assertSinErrores()

    def test_acceso_a_miembro_con_this(self):
        self.assertEqual(self.c.check_member_access(self.c.check_this(), "saldo"),
                         ts.INTEGER)
        self.assertSinErrores()

    def test_this_fuera_de_metodo_reporta_error(self):
        self.c.exit_function()
        self.metodo_abierto = False
        self.assertEqual(self.c.check_this(), ts.ERROR)
        self.assertMensaje("'this' solo puede usarse dentro de un método de clase")


class TestIndicesDeArreglos(BaseChecker):

    def test_indice_valido_devuelve_el_tipo_del_elemento(self):
        self.assertEqual(self.c.check_index("integer[]", ts.INTEGER), ts.INTEGER)
        self.assertSinErrores()

    def test_indice_con_tipo_no_integer(self):
        self.c.check_index("string[]", ts.BOOLEAN)
        self.assertMensaje("el índice de un arreglo debe ser de tipo 'integer'")

    def test_indice_sobre_tipo_no_arreglo(self):
        self.assertEqual(self.c.check_index(ts.INTEGER, ts.INTEGER), ts.ERROR)
        self.assertMensaje("no se puede indexar")

    def test_asignacion_de_elemento_valida(self):
        self.assertEqual(self.c.check_index_assign("integer[]", ts.INTEGER, ts.INTEGER),
                         ts.INTEGER)
        self.assertSinErrores()

    def test_asignacion_de_elemento_con_tipo_incorrecto(self):
        self.assertEqual(self.c.check_index_assign("integer[]", ts.INTEGER, ts.STRING),
                         ts.ERROR)
        self.assertMensaje("no se puede asignar a un elemento del arreglo")

    def test_asignacion_de_elemento_a_tipo_no_arreglo(self):
        self.assertEqual(self.c.check_index_assign(ts.STRING, ts.INTEGER, ts.INTEGER),
                         ts.ERROR)
        self.assertMensaje("no se puede indexar")


class TestArreglosConHerencia(BaseChecker):
    """El sistema de tipos puro no conoce la herencia: los arreglos literales
    no mezclan una clase y su subclase (los objetos sí, vía assignable)."""

    def setUp(self):
        super().setUp()
        self.crear_clase("Figura")
        self.crear_clase("Circulo", parent="Figura")

    def test_arreglo_literal_de_clase_y_subclase(self):
        self.assertEqual(self.c.array_literal(["Circulo", "Figura"]), ts.ERROR)
        self.assertMensaje("los elementos del arreglo deben ser del mismo tipo")

    def test_arreglo_literal_homogeneo_de_clase(self):
        self.assertEqual(self.c.array_literal(["Circulo", "Circulo"]), "Circulo[]")
        self.assertSinErrores()