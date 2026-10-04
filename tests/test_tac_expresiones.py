"""
Tests de la Etapa 1 de la generación de código intermedio:
expresiones, declaraciones, asignaciones, print y el
esqueleto de funciones.

Cada programa se analiza con la pipeline completa (léxico +
sintáctico + semántico + memoria) y se compara el TAC
generado con una salida esperada línea por línea, además de
las métricas de reciclaje de temporales.

Corre con: python -m unittest discover -s tests -v
"""

import os
import sys
import unittest

_BASE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(_BASE, "..", "src", "compiler"))

from pipeline import analizar_codigo


class BaseTACExpresiones(unittest.TestCase):

    def analizar(self, codigo):
        resultado = analizar_codigo("test.cps", codigo)
        self.assertTrue(resultado.es_valido,
                        [str(e) for e in resultado.errores])
        self.assertTrue(resultado.genero_tac)
        return resultado

    def lineas_tac(self, codigo):
        """Las instrucciones del TAC, una por línea (sin
        numerar y sin la sangría de las no-etiquetas)."""
        return [linea.strip()
                for linea in self.analizar(codigo)
                .tac.como_texto().splitlines()]


class TestDeclaracionesYAsignaciones(BaseTACExpresiones):

    def test_declaracion_con_inicializador(self):
        self.assertEqual(self.lineas_tac("let x: integer = 5;"),
                         ["global+0 = 5"])

    def test_declaracion_sin_inicializador_no_emite_nada(self):
        self.assertEqual(self.lineas_tac(
            "let x: integer;\nx = 7;"),
            ["global+0 = 7"])

    def test_constante_asignacion_y_suma(self):
        self.assertEqual(self.lineas_tac(
            "const MAX: integer = 100;\n"
            "var total: integer = 0;\n"
            "total = total + MAX;"),
            ["global+0 = 100",
             "global+4 = 0",
             "t1 = global+4 + global+0",
             "global+4 = t1"])

    def test_asignacion_encadenada(self):
        """El valor de 'y = x + y' es lo que se asigna a x."""
        self.assertEqual(self.lineas_tac(
            "let x: integer = 1;\n"
            "let y: integer = 2;\n"
            "x = y = x + y;"),
            ["global+0 = 1",
             "global+4 = 2",
             "t1 = global+0 + global+4",
             "global+4 = t1",
             "global+0 = t1"])


class TestExpresiones(BaseTACExpresiones):

    def test_precedencia_de_operadores(self):
        self.assertEqual(self.lineas_tac(
            "let a: integer = 2;\n"
            "let b: integer = 3;\n"
            "let c: integer = 4;\n"
            "let r: integer = a + b * c;"),
            ["global+0 = 2",
             "global+4 = 3",
             "global+8 = 4",
             "t1 = global+4 * global+8",
             "t1 = global+0 + t1",
             "global+12 = t1"])

    def test_los_parentesis_no_cambian_el_resultado(self):
        self.assertEqual(self.lineas_tac(
            "let x: integer = (1 + 2) * 3;"),
            ["t1 = 1 + 2",
             "t1 = t1 * 3",
             "global+0 = t1"])

    def test_menos_unario_y_negacion(self):
        self.assertEqual(self.lineas_tac(
            "let x: integer = 5;\n"
            "let y: integer = -x;\n"
            "let z: boolean = !true;"),
            ["global+0 = 5",
             "t1 = -global+0",
             "global+4 = t1",
             "t1 = !true",
             "global+8 = t1"])

    def test_comparaciones_y_logicas(self):
        self.assertEqual(self.lineas_tac(
            "let a: boolean = true;\n"
            "let b: boolean = false;\n"
            "let c: boolean = a && b || a == true;"),
            ["global+0 = true",
             "global+1 = false",
             "t1 = global+0 && global+1",
             "t2 = global+0 == true",
             "t1 = t1 || t2",
             "global+2 = t1"])

    def test_ternario(self):
        """Ambas ramas asignan al mismo temporal; el temporal
        de la condición se recicla como resultado."""
        self.assertEqual(self.lineas_tac(
            "let x: integer = 5;\n"
            "let y: integer = x > 3 ? 10 : 20;"),
            ["global+0 = 5",
             "t1 = global+0 > 3",
             "ifFalse t1 goto L1_ternario_sino",
             "t1 = 10",
             "goto L2_ternario_fin",
             "L1_ternario_sino:",
             "t1 = 20",
             "L2_ternario_fin:",
             "global+4 = t1"])


class TestReciclajeDeTemporales(BaseTACExpresiones):

    RECICLAJE = (
        "let a: integer = 1;\n"
        "let b: integer = 2;\n"
        "let c: integer = 3;\n"
        "let d: integer = 4;\n"
        "let e: integer = 5;\n"
        "let f: integer = 6;\n"
        "let r: integer = (a + b) * (c + d) - (e + f);\n"
    )

    def test_expresion_larga_con_reciclaje(self):
        """(a+b)*(c+d)-(e+f): 5 temporales sin reciclaje,
        2 con reciclaje (DISENO_TAC.md §3)."""
        self.assertEqual(self.lineas_tac(self.RECICLAJE),
                         ["global+0 = 1",
                          "global+4 = 2",
                          "global+8 = 3",
                          "global+12 = 4",
                          "global+16 = 5",
                          "global+20 = 6",
                          "t1 = global+0 + global+4",
                          "t2 = global+8 + global+12",
                          "t1 = t1 * t2",
                          "t2 = global+16 + global+20",
                          "t1 = t1 - t2",
                          "global+24 = t1"])

    def test_metricas_del_reciclaje(self):
        resultado = self.analizar(self.RECICLAJE)
        self.assertEqual(resultado.temporales["nombres_creados"], 2)
        self.assertEqual(resultado.temporales["reutilizaciones"], 3)
        self.assertEqual(resultado.temporales["pico_simultaneo"], 2)
        self.assertEqual(resultado.temporales["ahorro"], 3)
        self.assertEqual(resultado.temporales["vivos_al_final"], 0)


class TestPrint(BaseTACExpresiones):

    def test_print_de_variable_y_de_expresion(self):
        self.assertEqual(self.lineas_tac(
            "let x: integer = 5;\n"
            "print(x);\n"
            "print(x + 1);"),
            ["global+0 = 5",
             "print global+0",
             "t1 = global+0 + 1",
             "print t1"])


class TestFunciones(BaseTACExpresiones):

    def test_funcion_con_retorno(self):
        self.assertEqual(self.lineas_tac(
            "function suma(a: integer, b: integer): integer {\n"
            "  return a + b;\n"
            "}"),
            ["function suma:",
             "t1 = fp+16 + fp+20",
             "return t1",
             "endfunction suma"])

    def test_funcion_void(self):
        self.assertEqual(self.lineas_tac(
            "function saludar() {\n"
            "  print(\"hola\");\n"
            "}"),
            ["function saludar:",
             "print \"hola\"",
             "endfunction saludar"])

    def test_funcion_anidada_captura_el_entorno(self):
        """La variable capturada se referencia por su nombre
        (vive en el marco de la contenedora; el código
        objeto la alcanza por el enlace estático, §7) y el
        parámetro por su dirección."""
        self.assertEqual(self.lineas_tac(
            "function contador(): integer {\n"
            "  var base: integer = 10;\n"
            "  function interno(x: integer): integer {\n"
            "    return base + x;\n"
            "  }\n"
            "  return base;\n"
            "}"),
            ["function contador:",
             "fp+16 = 10",
             "function contador.interno:",
             "t1 = base + fp+16",
             "return t1",
             "endfunction contador.interno",
             "return fp+16",
             "endfunction contador"])


class TestGanchosPendientes(BaseTACExpresiones):

    def test_los_atributos_de_clase_no_generan_codigo(self):
        """Son parte del layout del objeto (memoria.py),
        no sentencias ejecutables: la declaración del atributo no emite
        nada, solo el método que lo asigna a través de 'this'."""
        self.assertEqual(self.lineas_tac(
            "class Punto {\n"
            "  var x: integer;\n"
            "  function constructor() {\n"
            "    this.x = 0;\n"
            "  }\n"
            "}"),
            ["function Punto.constructor:",
             "this.x = 0",
             "endfunction Punto.constructor"])

    def test_new_reserva_el_objeto(self):
        """Sin constructor en la cadena de herencia solo se emite el new."""
        self.assertEqual(
            self.lineas_tac(
                "class Punto {}\n"
                "let p: Punto = new Punto();\n"),
            ["t1 = new Punto",
             "global+0 = t1"])


class TestVistaDelIDE(BaseTACExpresiones):

    def test_filas_para_la_tabla_de_cuadruplos(self):
        resultado = self.analizar("let x: integer = 5;")
        self.assertEqual(resultado.tac_filas, [
            {"#": 0, "Operación": "=", "Arg1": "5", "Arg2": "_",
             "Resultado": "global+0", "Instrucción": "global+0 = 5"},
        ])