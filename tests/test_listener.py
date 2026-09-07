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

    def test_programa_media_ok_media(self):
        codigo = open(os.path.join(RUTA_EJEMPLOS, "ok_media.cps")).read()
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


class TestSinErroresSemanticos(BasePipeline):

    def test_codigo_con_error_sintactico_no_genera_semanticos(self):
        resultado = self.analizar('var x = ;')
        self.assertEqual(self.semantico(resultado), [])
        self.assertTrue(any(e.tipo == "Sintáctico" for e in resultado.errores))


if __name__ == "__main__":
    unittest.main()