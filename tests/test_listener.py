"""
Tests de integración del listener semántico: se analiza código Compiscript con
el pipeline completo (léxico + sintáctico + semántico) y se comprueban los
errores semánticos producidos por programas reales.

Corre con: python -m unittest discover -s tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "compiler"))

from pipeline import analizar_codigo

RUTA_EJEMPLOS = os.path.join(os.path.dirname(__file__), "..", "ejemplos")


VALIDO_CLASES = """
class Punto {
  var x: integer;
  var y: integer;
  function constructor(x: integer, y: integer) {
    this.x = x;
    this.y = y;
  }
  function sumar(): integer {
    return this.x + this.y;
  }
}

class Punto3D : Punto {
  var z: integer;
  function constructor(x: integer, y: integer, z: integer) {
    this.x = x;
    this.y = y;
    this.z = z;
  }
  function total(): integer {
    return this.sumar() + this.z;
  }
}

function principal(): integer {
  var origen = new Punto(0, 0);
  var lejano = new Punto3D(1, 2, 3);
  var puntos: Punto[] = [origen, new Punto(4, 4)];
  var indices: integer[] = [0, 1, 2];
  indices[0] = lejano.total();
  return puntos[0].x + indices[0];
}
"""


class BasePipeline(unittest.TestCase):

    def analizar(self, codigo):
        return analizar_codigo("test.cps", codigo)

    def semantico(self, resultado):
        return [e.descripcion for e in resultado.errores if e.tipo == "Semántico"]

    def assertValido(self, resultado):
        self.assertEqual(len(resultado.errores), 0,
                         "\n".join(str(e) for e in resultado.errores))

    def assertErrorSemantico(self, codigo, fragmento):
        resultado = self.analizar(codigo)
        mensajes = self.semantico(resultado)
        self.assertTrue(any(fragmento in m for m in mensajes),
                        f"No se encontró '{fragmento}'. Errores: {mensajes}")
        return mensajes


class TestProgramasValidos(BasePipeline):

    def test_programa_semantica_ok_semantica(self):
        codigo = open(os.path.join(RUTA_EJEMPLOS, "ok_semantica.cps")).read()
        self.assertValido(self.analizar(codigo))

    def test_clases_objetos_y_listas(self):
        self.assertValido(self.analizar(VALIDO_CLASES))

    def test_for_sin_inicializador_ni_condicion_no_reporta_condicion(self):
        codigo = """
function f() {
  var i: integer = 0;
  for (;; i = i + 1) {
    if (i == 10) { break; }
  }
}
"""
        self.assertValido(self.analizar(codigo))


class TestFunciones(BasePipeline):

    def test_funcion_recursiva_factorial(self):
        codigo = """
function factorial(n: integer): integer {
  if (n <= 1) { return 1; }
  return n * factorial(n - 1);
}
function uso() {
  var x: integer = factorial(5);
}
"""
        self.assertValido(self.analizar(codigo))

    def test_funcion_anidada_captura_variables_del_entorno(self):
        codigo = """
function externa(): integer {
  var contador: integer = 10;
  function interna(x: integer): integer {
    return contador + x;
  }
  return interna(5);
}
"""
        self.assertValido(self.analizar(codigo))

    def test_funcion_anidada_no_ve_variables_de_otro_ambito(self):
        self.assertErrorSemantico(
            'function a() { var x: integer = 1; }'
            'function b() { var y: integer = x; }',
            "'x' no ha sido declarado")

    def test_return_fuera_de_funcion(self):
        self.assertErrorSemantico(
            "return 5;",
            "'return' solo puede usarse dentro de una función")

    def test_usar_funcion_como_valor_reporta_error(self):
        self.assertErrorSemantico(
            'function f(): integer { return 2; }'
            'function g() { var x: integer = f * 2; }',
            "la función 'f' debe llamarse con paréntesis")

    def test_usar_clase_como_valor_reporta_error(self):
        self.assertErrorSemantico(
            'class A { } function g() { var x: integer = A; }',
            "la clase 'A' debe instanciarse con 'new'")


class TestReglasDeTipos(BasePipeline):

    def test_operacion_invalida_entre_tipos(self):
        self.assertErrorSemantico(
            'var x: integer = 1; var y = x + "hola";',
            "no se puede aplicar '+'")

    def test_inicializacion_de_tipo_incorrecto(self):
        self.assertErrorSemantico(
            'var x: integer = "texto";',
            "no se puede inicializar 'x'")

    def test_retorno_de_tipo_incorrecto(self):
        self.assertErrorSemantico(
            'function f(): integer { return "hola"; }',
            "el return de 'f'")

    def test_argumento_de_tipo_incorrecto(self):
        self.assertErrorSemantico(
            'function suma(a: integer, b: integer): integer { return a + b; }'
            'function f() { suma(1, "x"); }',
            "argumento 2 ('b') de 'suma'")

    def test_condicion_de_if_no_boolean(self):
        self.assertErrorSemantico(
            'function f() { var x: integer = 1; if (x) { print(x); } }',
            "la condición de 'if' debe ser boolean")

    def test_condicion_de_for_no_boolean(self):
        self.assertErrorSemantico(
            'function f(n: integer) { for (var i: integer = 0; n; i = i + 1) {} }',
            "la condición de 'for' debe ser boolean")

    def test_condicion_de_ternario_no_boolean(self):
        self.assertErrorSemantico(
            'var x: integer = 5; var y = x ? 1 : 2;',
            "la condición de 'ternario' debe ser boolean")

    def test_indice_sobre_tipo_no_arreglo(self):
        self.assertErrorSemantico(
            'var x: integer = 1; var y = x[0];',
            "no se puede indexar")

    def test_indice_de_tipo_no_integer(self):
        self.assertErrorSemantico(
            'var x: integer[] = [1, 2]; var y = x["a"];',
            "el índice de un arreglo debe ser de tipo 'integer'")

    def test_asignacion_de_elemento_con_tipo_incorrecto(self):
        self.assertErrorSemantico(
            'var x: integer[] = [1, 2]; x[0] = "a";',
            "no se puede asignar a un elemento del arreglo")


class TestDeclaracionesYAmbitos(BasePipeline):

    def test_variable_no_declarada(self):
        self.assertErrorSemantico('var y = inexistente + 1;', "'inexistente' no ha sido declarado")

    def test_redeclaracion_en_el_mismo_ambito(self):
        self.assertErrorSemantico(
            'var x: integer = 1; var x: integer = 2;',
            "'x' ya fue declarado en este ámbito")

    def test_break_fuera_de_bucle(self):
        self.assertErrorSemantico('break;', "'break' solo puede usarse dentro de un bucle")

    def test_continue_fuera_de_bucle(self):
        self.assertErrorSemantico('continue;', "'continue' solo puede usarse dentro de un bucle")

    def test_return_fuera_de_funcion(self):
        self.assertErrorSemantico('return 5;', "'return' solo puede usarse dentro de una función")

    def test_funcion_que_no_retorna_valor(self):
        self.assertErrorSemantico(
            'function f(): integer { var x: integer = 1; }',
            "la función 'f' debe retornar un valor")

    def test_reasignacion_de_constante(self):
        self.assertErrorSemantico(
            'const PI: integer = 3; PI = 4;',
            "no se puede reasignar la constante 'PI'")

    def test_foreach_sobre_no_arreglo(self):
        self.assertErrorSemantico(
            'foreach (x in 5) {}',
            "'foreach' requiere un arreglo")

    def test_case_incompatible_con_el_switch(self):
        self.assertErrorSemantico(
            'var x: integer = 1; switch (x) { case "texto": print("hola"); }',
            "no es comparable con el switch")


class TestClasesYObjetos(BasePipeline):

    def test_miembro_inexistente(self):
        self.assertErrorSemantico(
            'class A { var x: integer; }'
            'function f() { var a = new A(); var y = a.noExiste; }',
            "la clase 'A' no tiene un miembro llamado 'noExiste'")

    def test_metodo_inexistente(self):
        self.assertErrorSemantico(
            'class A { var x: integer; }'
            'function f() { var a = new A(); a.metodo(); }',
            "la clase 'A' no tiene un método llamado 'metodo'")

    def test_argumentos_incorrectos_de_metodo(self):
        self.assertErrorSemantico(
            'class A { function m(a: integer, b: integer): integer { return a + b; } }'
            'function f() { var a = new A(); a.m(1); }',
            "'m' espera 2 argumento(s) y recibió 1")

    def test_acceso_a_atributo_de_tipo_no_clase(self):
        self.assertErrorSemantico(
            'var x: integer = 5; var y = x.nombre;',
            "no es una clase")

    def test_asignacion_a_miembro_inexistente(self):
        self.assertErrorSemantico(
            'class A { var x: integer; }'
            'function f() { var a = new A(); a.noExiste = 5; }',
            "la clase 'A' no tiene un miembro llamado 'noExiste'")

    def test_asignacion_a_metodo_y_constante(self):
        self.assertErrorSemantico(
            'class A { const NOMBRE: string = "a"; var x: integer; }'
            'function f() { var a = new A(); a.NOMBRE = "b"; }',
            "no se puede reasignar la constante 'NOMBRE'")

    def test_asignacion_de_tipo_incorrecto_a_atributo(self):
        self.assertErrorSemantico(
            'class A { var x: integer; }'
            'function f() { var a = new A(); a.x = "texto"; }',
            "no se puede asignar a 'A.x'")

    def test_new_de_clase_no_declarada(self):
        self.assertErrorSemantico(
            'var a = new Fantasma();',
            "la clase 'Fantasma' no ha sido declarada")

    def test_new_con_argumentos_incorrectos(self):
        self.assertErrorSemantico(
            'class A { function constructor(x: integer) { } }'
            'var a = new A();',
            "'constructor' espera 1 argumento(s) y recibió 0")

    def test_this_fuera_de_un_metodo(self):
        self.assertErrorSemantico(
            'function f() { var y = this; }',
            "'this' solo puede usarse dentro de un método de clase")

    def test_constructor_no_puede_declarar_tipo_de_retorno(self):
        self.assertErrorSemantico(
            'class A { function constructor(): integer { } }',
            "el constructor no puede declarar un tipo de retorno")

    def test_constructor_no_puede_llamarse_directamente(self):
        self.assertErrorSemantico(
            'class A { function constructor() { }'
            '  function m() { constructor(); }'
            '}',
            "el constructor 'constructor' no puede llamarse directamente")

    def test_superclase_no_declarada(self):
        self.assertErrorSemantico(
            'class B : Fantasma { }',
            "la clase 'Fantasma' no ha sido declarada")


class TestFloats(BasePipeline):

    def test_declaracion_de_float_con_literal(self):
        self.assertValido(self.analizar("let f: float = 1.5;"))

    def test_operaciones_mixtas_entero_y_float(self):
        self.assertValido(self.analizar("var x = 2.5 + 1;"))
        self.assertValido(self.analizar("var x = 1 * 2.0;"))

    def test_menos_unario_sobre_float(self):
        self.assertValido(self.analizar("var x = -2.5;"))

    def test_float_no_es_asignable_a_integer(self):
        self.assertErrorSemantico(
            "let n: integer = 1.5;",
            "se esperaba 'integer' y se recibió 'float'")

    def test_integer_si_es_asignable_a_float(self):
        self.assertValido(self.analizar("let f: float = 1;"))

    def test_operacion_mixta_float_y_string_es_invalida(self):
        self.assertErrorSemantico(
            "var x = 1.5 * \"hola\";",
            "no se puede aplicar '*' entre 'float' y 'string'")

    def test_arreglo_de_floats_valido(self):
        self.assertValido(self.analizar("let nums: float[] = [1, 2.0];"))

    def test_indice_de_arreglo_no_puede_ser_float(self):
        self.assertErrorSemantico(
            "let arr: integer[] = [1]; var x = arr[1.5];",
            "el índice de un arreglo debe ser de tipo 'integer', no 'float'")

    def test_float_no_es_condicion_boolean(self):
        self.assertErrorSemantico(
            "function f() { if (1.5) { } }",
            "la condición de 'if' debe ser boolean")


class TestReglasGenerales(BasePipeline):

    def test_codigo_muerto_despues_de_return(self):
        self.assertErrorSemantico(
            'function f(): integer { return 1; var x: integer = 2; }',
            "código inalcanzable")

    def test_codigo_muerto_despues_de_break(self):
        self.assertErrorSemantico(
            'function f(flag: boolean) { while (flag) { break; print("x"); } }',
            "código inalcanzable")

    def test_codigo_muerto_despues_de_continue(self):
        self.assertErrorSemantico(
            'function f() { for (var i: integer = 0; i < 3; i = i + 1) '
            '{ continue; print("x"); } }',
            "código inalcanzable")

    def test_return_dentro_de_if_no_mata_el_resto(self):
        self.assertValido(self.analizar(
            'function f(x: integer): integer { if (x > 0) { return 1; } '
            'var y: integer = 2; return y; }'))

    def test_case_duplicado_en_switch(self):
        self.assertErrorSemantico(
            'function f(n: integer) { switch (n) { case 1: print("a"); '
            'case 1: print("b"); } }',
            "el 'case' con valor '1' ya fue declarado en este switch")

    def test_case_distintos_en_switch_no_es_error(self):
        self.assertValido(self.analizar(
            'function f(n: integer) { switch (n) { case 1: print("a"); '
            'case 2: print("b"); } }'))

    def test_autocomparaciones_sin_sentido(self):
        self.assertErrorSemantico(
            'function f(a: integer) { var x = a == a; }',
            "comparación sin sentido: 'a' se compara consigo misma")
        self.assertErrorSemantico(
            'function f(a: integer) { var x = a != a; }',
            "comparación sin sentido: 'a' se compara consigo misma")

    def test_comparacion_de_variables_distintas_es_valida(self):
        self.assertValido(self.analizar(
            'function f(a: integer, b: integer) { var x = a == b; }'))

    def test_division_por_literal_cero(self):
        self.assertErrorSemantico(
            'function f(a: integer) { var x = a / 0; }',
            "división por cero")

    def test_modulo_por_literal_cero(self):
        self.assertErrorSemantico(
            'function f(a: integer) { var x = a % 0; }',
            "módulo por cero")

    def test_division_por_literal_no_cero_es_valida(self):
        self.assertValido(self.analizar(
            'function f(a: integer) { var x = a / 2; }'))

    def test_condicion_literal_en_if(self):
        self.assertErrorSemantico(
            'function f() { if (true) { print("x"); } }',
            "la condición de 'if' es una constante ('true')")

    def test_condicion_literal_en_while(self):
        self.assertErrorSemantico(
            'function f() { while (false) { } }',
            "la condición de 'while' es una constante ('false')")

    def test_condicion_literal_en_for(self):
        self.assertErrorSemantico(
            'function f() { for (; true;) { } }',
            "la condición de 'for' es una constante ('true')")

    def test_condicion_con_variable_no_es_error(self):
        self.assertValido(self.analizar(
            'function f(flag: boolean) { if (flag) { print("x"); } }'))

    def test_print_de_expression_void(self):
        self.assertErrorSemantico(
            'function vacia() { }'
            'function f() { print(vacia()); }',
            "'print' no puede imprimir una expresión de tipo 'void'")

    def test_print_de_valor_normal_no_es_error(self):
        self.assertValido(self.analizar(
            'function f() { print(42); }'))


class TestSinErroresSemanticos(BasePipeline):

    def test_codigo_con_error_sintactico_no_genera_semanticos(self):
        resultado = self.analizar('var x = ;')
        self.assertEqual(self.semantico(resultado), [])
        self.assertTrue(any(e.tipo == "Sintáctico" for e in resultado.errores))


class TestEjemplosDeLaRubrica(BasePipeline):
    """Los ejemplos del repo son la demostración de la rúbrica: no deben
    degradarse sin que los tests se enteren."""

    def _leer(self, nombre):
        with open(os.path.join(RUTA_EJEMPLOS, nombre), encoding="utf-8") as f:
            return f.read()

    def test_ok_semantica_es_valido(self):
        self.assertValido(self.analizar(self._leer("ok_semantica.cps")))

    def test_ok_semantica_construye_ambitos(self):
        resultado = self.analizar(self._leer("ok_semantica.cps"))
        ambitos = [fila["Ámbito"] for fila in resultado.ambitos]
        self.assertTrue(any(a.startswith("[global]") for a in ambitos))
        self.assertTrue(any("[class] Empleado" in a for a in ambitos))
        self.assertTrue(any("[function] factorial" in a for a in ambitos))
        self.assertTrue(any("[function] contador" in a for a in ambitos))
        self.assertTrue(any("[function] interno" in a for a in ambitos))
        self.assertTrue(any("[block]" in a for a in ambitos))

    def test_errores_semanticos_baja_son_solo_semanticos(self):
        resultado = self.analizar(self._leer("errores_semanticos_baja.cps"))
        self.assertFalse(resultado.es_valido)
        self.assertEqual({e.tipo for e in resultado.errores}, {"Semántico"})
        mensajes = self.semantico(resultado)
        self.assertEqual(len(mensajes), 5)

    def test_errores_semanticos_baja_mensajes(self):
        self.assertErrorSemantico(self._leer("errores_semanticos_baja.cps"),
                                  "se esperaba 'integer' y se recibió 'string'")
        self.assertErrorSemantico(self._leer("errores_semanticos_baja.cps"),
                                  "'nombreInexistente' no ha sido declarado")
        self.assertErrorSemantico(self._leer("errores_semanticos_baja.cps"),
                                  "el índice de un arreglo debe ser de tipo 'integer'")

    def test_errores_semanticos_media_son_solo_semanticos(self):
        resultado = self.analizar(self._leer("errores_semanticos_media.cps"))
        self.assertFalse(resultado.es_valido)
        self.assertEqual({e.tipo for e in resultado.errores}, {"Semántico"})
        mensajes = self.semantico(resultado)
        self.assertEqual(len(mensajes), 7)

    def test_errores_semanticos_media_mensajes(self):
        codigo = self._leer("errores_semanticos_media.cps")
        self.assertErrorSemantico(codigo, "argumento 1 ('n') de 'factorial'")
        self.assertErrorSemantico(codigo, "argumento 1 ('cantidad') de 'depositar'")
        self.assertErrorSemantico(codigo, "la condición de 'if' debe ser boolean")
        self.assertErrorSemantico(codigo, "no puede imprimir una expresión de tipo 'void'")
        self.assertErrorSemantico(codigo, "comparación sin sentido: 'uno' se compara consigo misma")
        self.assertErrorSemantico(codigo, "el 'case' con valor '1' ya fue declarado")


if __name__ == "__main__":
    unittest.main()