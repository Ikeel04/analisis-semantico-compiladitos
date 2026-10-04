"""
Tests de la generación de código intermedio para clases y objetos:
new y constructores, atributos, this, llamadas a métodos, herencia e
inicializadores de atributos.

Cada programa se analiza con la pipeline completa y se compara el TAC
generado con una salida esperada línea por línea. Los esquemas están en
docs/DISENO_TAC.md §2 (Clases y objetos).

Convenciones que fijan estos tests:
  - el receptor de un método (o el objeto que construye 'new') viaja como
    primer 'param', y el N de 'call' lo cuenta;
  - 'this' es el nombre del receptor dentro de un método;
  - un método se llama por el nombre de la clase que lo DECLARA: el
    ancestro más cercano que lo define (enlace estático).

Corre con: python -m unittest discover -s tests -v
"""

import os
import sys
import unittest

_BASE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(_BASE, "..", "src", "compiler"))

from pipeline import analizar_codigo


class BaseTACClases(unittest.TestCase):

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


class TestNewYConstructor(BaseTACClases):

    def test_new_sin_constructor_solo_reserva_el_objeto(self):
        self.assertEqual(self.lineas_tac(
            "class Vacia { }\n"
            "let v: Vacia = new Vacia();"),
            ["t1 = new Vacia",
             "global+0 = t1"])

    def test_new_con_constructor_y_argumentos(self):
        """El objeto es el primer param; el N del call lo cuenta."""
        self.assertEqual(self.lineas_tac(
            "class Punto {\n"
            "  var x: integer;\n"
            "  var y: integer;\n"
            "  function constructor(x: integer, y: integer) {\n"
            "    this.x = x;\n"
            "    this.y = y;\n"
            "  }\n"
            "}\n"
            "let p: Punto = new Punto(1, 2);"),
            ["function Punto.constructor:",
             "this.x = fp+16",
             "this.y = fp+20",
             "endfunction Punto.constructor",
             "t1 = new Punto",
             "param t1",
             "param 1",
             "param 2",
             "call Punto.constructor, 3",
             "global+0 = t1"])

    def test_argumentos_calculados_no_pisan_al_objeto(self):
        """El temporal del objeto se pide antes de liberar los argumentos:
        si no, 'new' reciclaría el temporal del argumento y lo pisaría."""
        lineas = self.lineas_tac(
            "class Punto {\n"
            "  var x: integer;\n"
            "  function constructor(x: integer) { this.x = x; }\n"
            "}\n"
            "let a: integer = 3;\n"
            "let p: Punto = new Punto(a + 1);")
        self.assertEqual(lineas[-6:],
                         ["t1 = global+0 + 1",
                          "t2 = new Punto",
                          "param t2",
                          "param t1",
                          "call Punto.constructor, 2",
                          "global+8 = t2"])

    def test_constructor_heredado(self):
        """B no define constructor: se usa el de A, con el nombre de A."""
        lineas = self.lineas_tac(
            "class A {\n"
            "  var n: integer;\n"
            "  function constructor(n: integer) { this.n = n; }\n"
            "}\n"
            "class B : A { }\n"
            "let b: B = new B(7);")
        self.assertEqual(lineas[-5:],
                         ["t1 = new B",
                          "param t1",
                          "param 7",
                          "call A.constructor, 2",
                          "global+0 = t1"])

    def test_constructor_propio_de_la_subclase(self):
        lineas = self.lineas_tac(
            "class A {\n"
            "  var n: integer;\n"
            "  function constructor(n: integer) { this.n = n; }\n"
            "}\n"
            "class B : A {\n"
            "  var m: integer;\n"
            "  function constructor(n: integer, m: integer) {\n"
            "    this.n = n;\n"
            "    this.m = m;\n"
            "  }\n"
            "}\n"
            "let b: B = new B(1, 2);")
        self.assertEqual(lineas[-6:],
                         ["t1 = new B",
                          "param t1",
                          "param 1",
                          "param 2",
                          "call B.constructor, 3",
                          "global+0 = t1"])


class TestAtributos(BaseTACClases):

    def test_lectura_y_escritura_de_atributos(self):
        self.assertEqual(self.lineas_tac(
            "class P { var x: integer; var y: integer; }\n"
            "let p: P = new P();\n"
            "p.x = 5;\n"
            "let a: integer = p.x;\n"
            "p.y = p.x + 1;"),
            ["t1 = new P",
             "global+0 = t1",
             "global+0.x = 5",
             "t1 = global+0.x",
             "global+8 = t1",
             "t1 = global+0.x",
             "t1 = t1 + 1",
             "global+0.y = t1"])

    def test_this_en_los_metodos(self):
        self.assertEqual(self.lineas_tac(
            "class C {\n"
            "  var n: integer;\n"
            "  function inc() { this.n = this.n + 1; }\n"
            "}"),
            ["function C.inc:",
             "t1 = this.n",
             "t1 = t1 + 1",
             "this.n = t1",
             "endfunction C.inc"])

    def test_atributo_sin_this_usa_su_desplazamiento_en_el_objeto(self):
        """Dentro de un método, el atributo por su nombre es obj+N."""
        self.assertEqual(self.lineas_tac(
            "class C {\n"
            "  var n: integer;\n"
            "  function get(): integer { return n; }\n"
            "  function set(v: integer) { n = v; }\n"
            "}"),
            ["function C.get:",
             "return obj+0",
             "endfunction C.get",
             "function C.set:",
             "obj+0 = fp+16",
             "endfunction C.set"])

    def test_acceso_encadenado_lee_cada_eslabon(self):
        lineas = self.lineas_tac(
            "class Motor { var hp: integer; }\n"
            "class Auto { var motor: Motor; }\n"
            "let a: Auto = new Auto();\n"
            "a.motor = new Motor();\n"
            "a.motor.hp = 90;\n"
            "let h: integer = a.motor.hp;")
        self.assertEqual(lineas,
                         ["t1 = new Auto",
                          "global+0 = t1",
                          "t1 = new Motor",
                          "global+0.motor = t1",
                          "t1 = global+0.motor",
                          "t1.hp = 90",
                          "t1 = global+0.motor",
                          "t1 = t1.hp",
                          "global+8 = t1"])

    def test_atributo_arreglo_lectura_y_escritura_por_indice(self):
        """l.notas[1] = 9 lee el atributo (el arreglo) y escribe la celda."""
        lineas = self.lineas_tac(
            "class Lista { var notas: integer[]; }\n"
            "let l: Lista = new Lista();\n"
            "l.notas = [1, 2, 3];\n"
            "l.notas[1] = 9;\n"
            "let x: integer = l.notas[2];")
        self.assertEqual(lineas[-6:],
                         ["global+0.notas = t1",
                          "t1 = global+0.notas",
                          "t1[1] = 9",
                          "t1 = global+0.notas",
                          "t1 = t1[2]",
                          "global+8 = t1"])

    def test_arreglo_de_objetos(self):
        lineas = self.lineas_tac(
            "class Perro { var edad: integer; }\n"
            "let perros: Perro[] = [new Perro(), new Perro()];\n"
            "perros[0].edad = 9;\n"
            "let e: integer = perros[1].edad;")
        self.assertEqual(lineas[-5:],
                         ["t3 = global+0[0]",
                          "t3.edad = 9",
                          "t3 = global+0[1]",
                          "t3 = t3.edad",
                          "global+8 = t3"])


class TestMetodos(BaseTACClases):

    def test_metodo_void_no_tiene_resultado(self):
        lineas = self.lineas_tac(
            "class C {\n"
            "  var n: integer;\n"
            "  function inc() { this.n = this.n + 1; }\n"
            "}\n"
            "let c: C = new C();\n"
            "c.inc();")
        self.assertEqual(lineas[-2:],
                         ["param global+0",
                          "call C.inc, 1"])

    def test_metodo_con_argumentos_y_retorno(self):
        lineas = self.lineas_tac(
            "class C {\n"
            "  var n: integer;\n"
            "  function suma(k: integer): integer {\n"
            "    this.n = this.n + k;\n"
            "    return this.n;\n"
            "  }\n"
            "}\n"
            "let c: C = new C();\n"
            "let r: integer = c.suma(5);")
        self.assertEqual(lineas[-4:],
                         ["param global+0",
                          "param 5",
                          "t1 = call C.suma, 2",
                          "global+8 = t1"])

    def test_this_llama_a_otro_metodo_de_su_clase(self):
        self.assertEqual(self.lineas_tac(
            "class C {\n"
            "  function a(): integer { return 1; }\n"
            "  function b(): integer { return this.a() + 1; }\n"
            "}"),
            ["function C.a:",
             "return 1",
             "endfunction C.a",
             "function C.b:",
             "param this",
             "t1 = call C.a, 1",
             "t1 = t1 + 1",
             "return t1",
             "endfunction C.b"])

    def test_llamada_por_nombre_dentro_de_la_clase_pasa_this(self):
        lineas = self.lineas_tac(
            "class C {\n"
            "  function a(): integer { return 1; }\n"
            "  function b(): integer { return a() + 1; }\n"
            "}")
        self.assertEqual(lineas[4:6], ["param this",
                                       "t1 = call C.a, 1"])

    def test_metodo_sobre_un_elemento_de_arreglo(self):
        lineas = self.lineas_tac(
            "class A { function hablar(): string { return \"hola\"; } }\n"
            "let xs: A[] = [new A(), new A()];\n"
            "let s: string = xs[1].hablar();")
        self.assertEqual(lineas[-4:],
                         ["t3 = global+0[1]",
                          "param t3",
                          "t1 = call A.hablar, 1",
                          "global+8 = t1"])

    PROGRAMA_AUTO = (
        "class Motor {\n"
        "  var hp: integer;\n"
        "  function potencia(): integer { return this.hp; }\n"
        "}\n"
        "class Auto {\n"
        "  var motor: Motor;\n"
        "  function m(): Motor { return this.motor; }\n"
        "}\n"
        "let a: Auto = new Auto();\n")

    def test_llamadas_encadenadas(self):
        """a.m().potencia(): el resultado del primer call es el receptor
        del segundo. Su temporal no se libera hasta después del call, por
        eso el resultado es t2 y no t1."""
        lineas = self.lineas_tac(
            self.PROGRAMA_AUTO + "let p: integer = a.m().potencia();")
        self.assertEqual(lineas[-5:],
                         ["param global+0",
                          "t1 = call Auto.m, 1",
                          "param t1",
                          "t2 = call Motor.potencia, 1",
                          "global+8 = t2"])

    def test_metodo_sobre_un_atributo(self):
        lineas = self.lineas_tac(
            self.PROGRAMA_AUTO + "let q: integer = a.motor.potencia();")
        self.assertEqual(lineas[-4:],
                         ["t1 = global+0.motor",
                          "param t1",
                          "t2 = call Motor.potencia, 1",
                          "global+8 = t2"])


class TestHerencia(BaseTACClases):

    PROGRAMA = (
        "class A {\n"
        "  function f(): integer { return 1; }\n"
        "  function g(): integer { return 2; }\n"
        "  function h(): integer { return 3; }\n"
        "}\n"
        "class B : A {\n"
        "  function g(): integer { return 20; }\n"
        "}\n"
        "class C : B {\n"
        "  function h(): integer { return 30; }\n"
        "  function t(): integer {\n"
        "    return this.f() + this.g() + this.h();\n"
        "  }\n"
        "}\n"
        "let c: C = new C();\n")

    def test_metodo_heredado_se_llama_con_el_nombre_del_ancestro(self):
        lineas = self.lineas_tac(self.PROGRAMA + "let x: integer = c.f();")
        self.assertEqual(lineas[-3:],
                         ["param global+0",
                          "t1 = call A.f, 1",
                          "global+8 = t1"])

    def test_metodo_redefinido_gana_el_ancestro_mas_cercano(self):
        """g está en A y en B: desde C se resuelve en B (el más cercano)."""
        lineas = self.lineas_tac(self.PROGRAMA + "let y: integer = c.g();")
        self.assertEqual(lineas[-3:],
                         ["param global+0",
                          "t1 = call B.g, 1",
                          "global+8 = t1"])

    def test_metodo_de_la_propia_clase(self):
        lineas = self.lineas_tac(self.PROGRAMA + "let z: integer = c.h();")
        self.assertEqual(lineas[-3:],
                         ["param global+0",
                          "t1 = call C.h, 1",
                          "global+8 = t1"])

    def test_this_resuelve_cada_metodo_en_su_ancestro(self):
        lineas = self.lineas_tac(self.PROGRAMA)
        inicio = lineas.index("function C.t:")
        fin = lineas.index("endfunction C.t")
        self.assertEqual(lineas[inicio:fin + 1],
                         ["function C.t:",
                          "param this",
                          "t1 = call A.f, 1",
                          "param this",
                          "t2 = call B.g, 1",
                          "param this",
                          "t3 = call C.h, 1",
                          "t1 = t1 + t2",
                          "t1 = t1 + t3",
                          "return t1",
                          "endfunction C.t"])

    def test_atributos_heredados_se_acceden_por_nombre(self):
        self.assertEqual(self.lineas_tac(
            "class A { var n: integer; }\n"
            "class B : A { var m: integer; }\n"
            "let b: B = new B();\n"
            "b.n = 1;\n"
            "b.m = 2;\n"
            "let s: integer = b.n + b.m;"),
            ["t1 = new B",
             "global+0 = t1",
             "global+0.n = 1",
             "global+0.m = 2",
             "t1 = global+0.n",
             "t2 = global+0.m",
             "t1 = t1 + t2",
             "global+8 = t1"])

    def test_dos_subclases_resuelven_independientes(self):
        lineas = self.lineas_tac(
            "class Animal { function hablar(): string { return \"...\"; } }\n"
            "class Perro : Animal {\n"
            "  function hablar(): string { return \"guau\"; }\n"
            "}\n"
            "class Gato : Animal { }\n"
            "let p: Perro = new Perro();\n"
            "let g: Gato = new Gato();\n"
            "let a: string = p.hablar();\n"
            "let b: string = g.hablar();")
        self.assertIn("t1 = call Perro.hablar, 1", lineas)
        self.assertIn("t1 = call Animal.hablar, 1", lineas)


class TestInicializadoresDeAtributos(BaseTACClases):
    """Un atributo con valor inicial no puede quedar suelto en el cuerpo de
    la clase (todavía no hay objeto): su código va a Clase.__atributos, que
    'new' llama sobre cada objeto, la del padre primero."""

    def test_los_inicializadores_van_a_una_funcion_de_la_clase(self):
        self.assertEqual(self.lineas_tac(
            "class Cuenta {\n"
            "  var saldo: integer = 100 + 50;\n"
            "  const MAX: integer = 1000;\n"
            "  var libre: integer;\n"
            "}"),
            ["function Cuenta.__atributos:",
             "t1 = 100 + 50",
             "this.saldo = t1",
             "this.MAX = 1000",
             "endfunction Cuenta.__atributos"])

    def test_new_inicializa_primero_al_padre(self):
        lineas = self.lineas_tac(
            "class Base { var id: integer = 1; }\n"
            "class Cuenta : Base { var saldo: integer = 5; }\n"
            "let c: Cuenta = new Cuenta();")
        self.assertEqual(lineas[-6:],
                         ["t1 = new Cuenta",
                          "param t1",
                          "call Base.__atributos, 1",
                          "param t1",
                          "call Cuenta.__atributos, 1",
                          "global+0 = t1"])

    def test_inicializadores_corren_antes_del_constructor(self):
        lineas = self.lineas_tac(
            "class C {\n"
            "  var n: integer = 0;\n"
            "  function constructor(k: integer) { this.n = k; }\n"
            "}\n"
            "let c: C = new C(4);")
        self.assertEqual(lineas[-7:],
                         ["t1 = new C",
                          "param t1",
                          "call C.__atributos, 1",
                          "param t1",
                          "param 4",
                          "call C.constructor, 2",
                          "global+0 = t1"])

    def test_clase_sin_inicializadores_no_genera_la_funcion(self):
        lineas = self.lineas_tac(
            "class P { var x: integer; }\n"
            "let p: P = new P();")
        self.assertFalse(any("__atributos" in linea for linea in lineas))

    def test_el_temporal_del_inicializador_no_se_fuga(self):
        resultado = self.analizar(
            "class Cuenta { var saldo: integer = 100 + 50; }\n"
            "let c: Cuenta = new Cuenta();")
        self.assertEqual(resultado.temporales["vivos_al_final"], 0)


class TestClasesYReciclaje(BaseTACClases):

    def test_no_quedan_temporales_vivos(self):
        resultado = self.analizar(
            "class Motor { var hp: integer; }\n"
            "class Auto {\n"
            "  var motor: Motor;\n"
            "  function m(): Motor { return this.motor; }\n"
            "}\n"
            "let a: Auto = new Auto();\n"
            "a.motor = new Motor();\n"
            "a.motor.hp = 90;\n"
            "let h: integer = a.m().hp;")
        self.assertEqual(resultado.temporales["vivos_al_final"], 0)

    def test_hay_reutilizacion_en_cadenas_de_acceso(self):
        resultado = self.analizar(
            "class Motor { var hp: integer; }\n"
            "class Auto { var motor: Motor; }\n"
            "let a: Auto = new Auto();\n"
            "a.motor = new Motor();\n"
            "let h: integer = a.motor.hp;")
        self.assertGreater(resultado.temporales["reutilizaciones"], 0)

    def test_no_queda_ningun_pendiente(self):
        resultado = self.analizar(
            "class Animal {\n"
            "  var nombre: string = \"x\";\n"
            "  function constructor(n: string) { this.nombre = n; }\n"
            "  function hablar(): string { return this.nombre; }\n"
            "}\n"
            "class Perro : Animal {\n"
            "  function hablar(): string { return this.nombre + \"!\"; }\n"
            "}\n"
            "let p: Perro = new Perro(\"t\");\n"
            "let s: string = p.hablar();\n"
            "p.nombre = \"r\";")
        self.assertNotIn("pendiente", resultado.tac_texto)
        self.assertNotIn("/*", resultado.tac_texto)


class TestCompuertaConClases(unittest.TestCase):

    def test_metodo_inexistente_no_genera_tac(self):
        r = analizar_codigo(
            "test.cps",
            "class A { var n: integer; }\n"
            "let a: A = new A();\n"
            "a.noExiste();")
        self.assertFalse(r.es_valido)
        self.assertFalse(r.genero_tac)
        self.assertEqual(r.tac_texto, "")

    def test_error_de_tipos_dentro_de_una_clase_no_genera_tac(self):
        r = analizar_codigo(
            "test.cps",
            "class A {\n"
            "  var n: integer;\n"
            "  function m() { this.n = \"texto\"; }\n"
            "}")
        self.assertFalse(r.es_valido)
        self.assertFalse(r.genero_tac)


if __name__ == "__main__":
    unittest.main(verbosity=2)
