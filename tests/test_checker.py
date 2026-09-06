"""
Batería de tests de las reglas semánticas: sistema de tipos aplicado al
programa, funciones y control de flujo. Cada regla tiene su caso exitoso y su
caso fallido.

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


class TestTiposEnOperaciones(BaseChecker):

    def test_aritmetica_valida_no_reporta(self):
        self.assertEqual(self.c.arithmetic("*", ts.INTEGER, ts.INTEGER), ts.INTEGER)
        self.assertSinErrores()

    def test_aritmetica_invalida_reporta_y_devuelve_error(self):
        self.assertEqual(self.c.arithmetic("-", ts.STRING, ts.INTEGER), ts.ERROR)
        self.assertErrores(1)
        self.assertMensaje("no se puede aplicar '-'")

    def test_logica_con_operando_no_boolean(self):
        self.assertEqual(self.c.logical("&&", ts.INTEGER, ts.BOOLEAN), ts.ERROR)
        self.assertMensaje("requiere operandos boolean")

    def test_comparacion_entre_tipos_incompatibles(self):
        self.assertEqual(self.c.comparison("==", ts.STRING, ts.INTEGER), ts.ERROR)
        self.assertMensaje("no se puede comparar")

    def test_comparacion_valida_devuelve_boolean(self):
        self.assertEqual(self.c.comparison("<", ts.INTEGER, ts.INTEGER), ts.BOOLEAN)
        self.assertSinErrores()

    def test_arreglo_literal_con_elementos_mezclados(self):
        self.assertEqual(self.c.array_literal([ts.INTEGER, ts.STRING]), ts.ERROR)
        self.assertMensaje("mismo tipo")

    def test_arreglo_literal_homogeneo(self):
        self.assertEqual(self.c.array_literal([ts.INTEGER, ts.INTEGER]), "integer[]")
        self.assertSinErrores()


class TestDeclaracionesYAsignaciones(BaseChecker):

    def test_inicializacion_con_tipo_correcto(self):
        self.c.declare_variable("x", ts.INTEGER, ts.INTEGER)
        self.assertSinErrores()

    def test_inicializacion_con_tipo_incorrecto(self):
        self.c.declare_variable("x", ts.INTEGER, ts.STRING)
        self.assertErrores(1)
        self.assertMensaje("no se puede inicializar 'x'")

    def test_tipo_inferido_del_inicializador(self):
        self.assertEqual(self.c.declare_variable("x", None, ts.STRING), ts.STRING)
        self.assertEqual(self.c.use_variable("x"), ts.STRING)

    def test_asignacion_compatible(self):
        self.c.declare_variable("x", ts.INTEGER, ts.INTEGER)
        self.assertEqual(self.c.check_assignment("x", ts.INTEGER), ts.INTEGER)
        self.assertSinErrores()

    def test_asignacion_incompatible(self):
        self.c.declare_variable("x", ts.INTEGER, ts.INTEGER)
        self.assertEqual(self.c.check_assignment("x", ts.BOOLEAN), ts.ERROR)
        self.assertMensaje("no se puede asignar a 'x'")

    def test_asignacion_a_variable_no_declarada(self):
        self.c.check_assignment("fantasma", ts.INTEGER)
        self.assertMensaje("'fantasma' no ha sido declarado")

    def test_variable_sin_tipo_infiere_en_la_primera_asignacion(self):
        self.c.declare_variable("x")                      # let x;
        self.c.check_assignment("x", ts.BOOLEAN)
        self.assertEqual(self.c.use_variable("x"), ts.BOOLEAN)
        self.assertSinErrores()


class TestConstantes(BaseChecker):

    def test_constante_inicializada_correctamente(self):
        self.c.declare_constant("PI", ts.INTEGER, ts.INTEGER)
        self.assertSinErrores()

    def test_constante_sin_inicializador(self):
        self.c.declare_constant("PI", ts.INTEGER, None, has_initializer=False)
        self.assertErrores(1)
        self.assertMensaje("debe inicializarse en su declaración")

    def test_constante_con_tipo_incompatible(self):
        self.c.declare_constant("PI", ts.INTEGER, ts.STRING)
        self.assertMensaje("no se puede inicializar la constante 'PI'")

    def test_no_se_puede_reasignar_una_constante(self):
        self.c.declare_constant("PI", ts.INTEGER, ts.INTEGER)
        self.c.check_assignment("PI", ts.INTEGER)
        self.assertMensaje("no se puede reasignar la constante 'PI'")


class TestFunciones(BaseChecker):

    def _declarar(self, nombre, params=(), retorno=None):
        return self.c.declare_function(nombre, list(params), retorno)

    def test_llamada_con_argumentos_correctos(self):
        self._declarar("suma", [("a", ts.INTEGER), ("b", ts.INTEGER)], ts.INTEGER)
        self.assertEqual(self.c.check_call("suma", [ts.INTEGER, ts.INTEGER]), ts.INTEGER)
        self.assertSinErrores()

    def test_llamada_con_numero_incorrecto_de_argumentos(self):
        self._declarar("suma", [("a", ts.INTEGER), ("b", ts.INTEGER)], ts.INTEGER)
        self.c.check_call("suma", [ts.INTEGER])
        self.assertMensaje("espera 2 argumento(s) y recibió 1")

    def test_llamada_con_tipo_de_argumento_incorrecto(self):
        self._declarar("saludar", [("nombre", ts.STRING)], ts.STRING)
        self.c.check_call("saludar", [ts.INTEGER])
        self.assertMensaje("argumento 1 ('nombre') de 'saludar'")

    def test_llamar_algo_que_no_es_funcion(self):
        self.c.declare_variable("x", ts.INTEGER, ts.INTEGER)
        self.c.check_call("x", [])
        self.assertMensaje("no es una función")

    def test_retorno_con_tipo_correcto(self):
        f = self._declarar("suma", [], ts.INTEGER)
        self.c.enter_function(f)
        self.c.check_return(ts.INTEGER)
        self.c.exit_function()
        self.assertSinErrores()

    def test_retorno_con_tipo_incorrecto(self):
        f = self._declarar("suma", [], ts.INTEGER)
        self.c.enter_function(f)
        self.c.check_return(ts.STRING)
        self.c.exit_function()
        self.assertMensaje("el return de 'suma'")

    def test_funcion_con_tipo_declarado_que_nunca_retorna(self):
        f = self._declarar("suma", [], ts.INTEGER)
        self.c.enter_function(f)
        self.c.exit_function()
        self.assertMensaje("debe retornar un valor de tipo 'integer'")

    def test_funcion_sin_tipo_de_retorno_no_puede_devolver_valor(self):
        f = self._declarar("imprimir", [], None)
        self.c.enter_function(f)
        self.c.check_return(ts.STRING)
        self.c.exit_function()
        self.assertMensaje("no declara tipo de retorno")

    def test_funcion_recursiva_puede_llamarse_a_si_misma(self):
        f = self._declarar("factorial", [("n", ts.INTEGER)], ts.INTEGER)
        self.c.enter_function(f)
        self.assertEqual(self.c.check_call("factorial", [ts.INTEGER]), ts.INTEGER)
        self.c.check_return(ts.INTEGER)
        self.c.exit_function()
        self.assertSinErrores()

    def test_funcion_anidada_captura_variables_del_entorno(self):
        externa = self._declarar("externa", [], ts.INTEGER)
        self.c.enter_function(externa)
        self.c.declare_variable("contador", ts.INTEGER, ts.INTEGER)
        interna = self._declarar("interna", [], ts.INTEGER)
        self.c.enter_function(interna)
        self.assertEqual(self.c.use_variable("contador"), ts.INTEGER)
        self.c.check_return(ts.INTEGER)
        self.c.exit_function()
        self.c.check_return(ts.INTEGER)
        self.c.exit_function()
        self.assertSinErrores()
        self.assertEqual(interna.extra["captured"], ["contador"])

    def test_variable_local_de_una_funcion_no_es_visible_afuera(self):
        f = self._declarar("f", [], None)
        self.c.enter_function(f)
        self.c.declare_variable("local", ts.INTEGER, ts.INTEGER)
        self.c.exit_function()
        self.c.use_variable("local")
        self.assertMensaje("'local' no ha sido declarado")

    def test_funciones_con_el_mismo_nombre(self):
        self._declarar("f", [], ts.INTEGER)
        self._declarar("f", [("a", ts.INTEGER)], ts.INTEGER)
        self.assertMensaje("no permite sobrecarga")

    def test_parametros_duplicados(self):
        f = self._declarar("f", [("a", ts.INTEGER), ("a", ts.STRING)], ts.INTEGER)
        self.c.enter_function(f)
        self.assertMensaje("'a' ya fue declarado")

    def test_argumentos_aceptan_null_en_parametro_de_clase(self):
        self._declarar("registrar", [("p", "Perro")], None)
        self.c.check_call("registrar", [ts.NULL])
        self.assertSinErrores()


class TestControlDeFlujo(BaseChecker):

    def test_condicion_boolean_es_valida(self):
        self.c.check_condition(ts.BOOLEAN, "if")
        self.assertSinErrores()

    def test_condicion_no_boolean_en_cada_construccion(self):
        for construccion in ("if", "while", "do-while", "for"):
            checker = SemanticChecker()
            checker.check_condition(ts.INTEGER, construccion)
            self.assertIn(f"la condición de '{construccion}'", checker.errors.as_text())

    def test_condicion_con_tipo_erroneo_no_reporta_de_nuevo(self):
        self.c.check_condition(ts.ERROR, "while")
        self.assertSinErrores()

    def test_break_y_continue_dentro_de_un_bucle(self):
        self.c.enter_loop()
        self.c.check_break()
        self.c.check_continue()
        self.c.exit_loop()
        self.assertSinErrores()

    def test_break_fuera_de_un_bucle(self):
        self.c.check_break()
        self.assertMensaje("'break' solo puede usarse dentro de un bucle")

    def test_continue_fuera_de_un_bucle(self):
        self.c.check_continue()
        self.assertMensaje("'continue' solo puede usarse dentro de un bucle")

    def test_break_despues_de_cerrar_el_bucle(self):
        self.c.enter_loop()
        self.c.exit_loop()
        self.c.check_break()
        self.assertErrores(1)

    def test_break_dentro_de_una_funcion_declarada_en_un_bucle(self):
        self.c.enter_loop()
        f = self.c.declare_function("f", [], None)
        self.c.enter_function(f)
        self.c.check_break()
        self.c.exit_function()
        self.c.exit_loop()
        self.assertMensaje("'break' solo puede usarse dentro de un bucle")

    def test_return_fuera_de_una_funcion(self):
        self.c.check_return(ts.INTEGER)
        self.assertMensaje("'return' solo puede usarse dentro de una función")

    def test_return_dentro_de_una_funcion(self):
        f = self.c.declare_function("f", [], ts.INTEGER)
        self.c.enter_function(f)
        self.c.check_return(ts.INTEGER)
        self.c.exit_function()
        self.assertSinErrores()

    def test_case_compatible_con_el_switch(self):
        self.c.check_switch_case(ts.INTEGER, ts.INTEGER)
        self.assertSinErrores()

    def test_case_incompatible_con_el_switch(self):
        self.c.check_switch_case(ts.INTEGER, ts.STRING)
        self.assertMensaje("no es comparable con el switch")

    def test_foreach_sobre_un_arreglo_declara_la_variable(self):
        self.c.declare_variable("notas", "integer[]", "integer[]")
        self.c.table.enter_scope("block")
        self.assertEqual(self.c.check_foreach("n", "integer[]"), ts.INTEGER)
        self.assertEqual(self.c.use_variable("n"), ts.INTEGER)
        self.assertSinErrores()

    def test_foreach_sobre_algo_que_no_es_arreglo(self):
        self.c.table.enter_scope("block")
        self.c.check_foreach("n", ts.INTEGER)
        self.assertMensaje("'foreach' requiere un arreglo")


class TestRecuperacionDeErrores(BaseChecker):

    def test_el_analisis_continua_y_acumula_varios_errores(self):
        self.c.arithmetic("+", ts.INTEGER, ts.BOOLEAN)
        self.c.check_break()
        self.c.check_return(ts.INTEGER)
        self.assertErrores(3)

    def test_un_error_no_genera_errores_derivados(self):
        indefinida = self.c.use_variable("y")           # único error real
        self.c.arithmetic("+", indefinida, ts.INTEGER)  # silencioso
        self.c.check_condition(indefinida, "if")        # silencioso
        self.assertErrores(1)

    def test_no_se_repite_el_mismo_error_en_la_misma_posicion(self):
        self.c.errors.add("mensaje", (3, 5))
        self.c.errors.add("mensaje", (3, 5))
        self.c.errors.add("mensaje", (4, 5))
        self.assertErrores(2)

    def test_los_errores_salen_ordenados_por_posicion(self):
        self.c.errors.add("segundo", (10, 0))
        self.c.errors.add("primero", (2, 0))
        self.assertEqual([i.message for i in self.c.errors], ["primero", "segundo"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
