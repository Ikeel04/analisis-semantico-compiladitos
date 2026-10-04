"""
Tests de la Etapa 2 de la generación de código intermedio:
control de flujo (if/else, while, do-while, for, foreach),
switch/case y try/catch.

Cada programa se analiza con la pipeline completa y se compara
el TAC generado con una salida esperada línea por línea. Los
esquemas que debe producir están en docs/DISENO_TAC.md §2.

Corre con: python -m unittest discover -s tests -v
"""

import os
import sys
import unittest

_BASE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(_BASE, "..", "src", "compiler"))

from pipeline import analizar_codigo


class BaseTACControl(unittest.TestCase):

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

    def sin_saltos_huerfanos(self, codigo):
        """Todo goto/if/ifFalse debe tener su etiqueta."""
        resultado = self.analizar(codigo)
        etiquetas = {c.arg1 for c in resultado.tac
                     if c.op == "label"}
        destinos = {c.resultado for c in resultado.tac
                    if c.op in ("goto", "if", "ifFalse")}
        self.assertEqual(destinos - etiquetas, set())


class TestIf(BaseTACControl):

    def test_if_else(self):
        self.assertEqual(self.lineas_tac(
            "let x: integer = 5;\n"
            "if (x > 3) {\n"
            "  print(x);\n"
            "} else {\n"
            "  print(0);\n"
            "}"),
            ["global+0 = 5",
             "t1 = global+0 > 3",
             "ifFalse t1 goto L1_if_else",
             "print global+0",
             "goto L2_if_fin",
             "L1_if_else:",
             "print 0",
             "L2_if_fin:"])

    def test_if_sin_else(self):
        """Sin 'else', el ifFalse salta directo al fin
        y desaparece el goto."""
        self.assertEqual(self.lineas_tac(
            "let x: integer = 5;\n"
            "if (x > 3) {\n"
            "  print(x);\n"
            "}"),
            ["global+0 = 5",
             "t1 = global+0 > 3",
             "ifFalse t1 goto L1_if_fin",
             "print global+0",
             "L1_if_fin:"])

    def test_if_anidado(self):
        """El 'if' interior vive dentro del 'then' del
        exterior (sin 'else', no hay goto ni etiqueta de
        bloque contrario)."""
        self.assertEqual(self.lineas_tac(
            "let x: integer = 5;\n"
            "if (x > 3) {\n"
            "  if (x > 4) {\n"
            "    print(x);\n"
            "  }\n"
            "}"),
            ["global+0 = 5",
             "t1 = global+0 > 3",
             "ifFalse t1 goto L1_if_fin",
             "t1 = global+0 > 4",
             "ifFalse t1 goto L2_if_fin",
             "print global+0",
             "L2_if_fin:",
             "L1_if_fin:"])


class TestWhile(BaseTACControl):

    def test_while(self):
        self.assertEqual(self.lineas_tac(
            "var i: integer = 0;\n"
            "while (i < 3) {\n"
            "  i = i + 1;\n"
            "}"),
            ["global+0 = 0",
             "L1_while_inicio:",
             "t1 = global+0 < 3",
             "ifFalse t1 goto L2_while_fin",
             "t1 = global+0 + 1",
             "global+0 = t1",
             "goto L1_while_inicio",
             "L2_while_fin:"])

    def test_ciclos_anidados(self):
        """El 'break' salta al ciclo más interno."""
        self.assertEqual(self.lineas_tac(
            "var i: integer = 0;\n"
            "while (i < 2) {\n"
            "  var j: integer = 0;\n"
            "  while (j < 2) {\n"
            "    if (j == 1) { break; }\n"
            "    j = j + 1;\n"
            "  }\n"
            "  i = i + 1;\n"
            "}"),
            ["global+0 = 0",
             "L1_while_inicio:",
             "t1 = global+0 < 2",
             "ifFalse t1 goto L2_while_fin",
             "global+4 = 0",
             "L3_while_inicio:",
             "t1 = global+4 < 2",
             "ifFalse t1 goto L4_while_fin",
             "t1 = global+4 == 1",
             "ifFalse t1 goto L5_if_fin",
             "goto L4_while_fin",
             "L5_if_fin:",
             "t1 = global+4 + 1",
             "global+4 = t1",
             "goto L3_while_inicio",
             "L4_while_fin:",
             "t1 = global+0 + 1",
             "global+0 = t1",
             "goto L1_while_inicio",
             "L2_while_fin:"])


class TestDoWhile(BaseTACControl):

    def test_do_while_con_continue(self):
        """La condición tiene etiqueta propia: 'continue'
        salta a ella, no al inicio (no re-ejecuta el cuerpo)."""
        self.assertEqual(self.lineas_tac(
            "var k: integer = 0;\n"
            "do {\n"
            "  k = k + 1;\n"
            "  if (k == 1) { continue; }\n"
            "} while (k < 3);"),
            ["global+0 = 0",
             "L1_dowhile_inicio:",
             "t1 = global+0 + 1",
             "global+0 = t1",
             "t1 = global+0 == 1",
             "ifFalse t1 goto L4_if_fin",
             "goto L3_dowhile_cond",
             "L4_if_fin:",
             "L3_dowhile_cond:",
             "t1 = global+0 < 3",
             "if t1 goto L1_dowhile_inicio",
             "L2_dowhile_fin:"])


class TestFor(BaseTACControl):

    def test_for_completo(self):
        self.assertEqual(self.lineas_tac(
            "for (let j: integer = 0; j < 3; j = j + 1) {\n"
            "  if (j == 1) { continue; }\n"
            "  print(j);\n"
            "}"),
            ["global+0 = 0",
             "L1_for_inicio:",
             "t1 = global+0 < 3",
             "ifFalse t1 goto L2_for_fin",
             "L3_for_paso:",
             "t1 = global+0 + 1",
             "global+0 = t1",
             "goto L1_for_inicio",
             "L4_for_cuerpo:",
             "t1 = global+0 == 1",
             "ifFalse t1 goto L5_if_fin",
             "goto L3_for_paso",
             "L5_if_fin:",
             "print global+0",
             "goto L3_for_paso",
             "L2_for_fin:"])

    def test_for_sin_paso(self):
        """Sin paso, 'continue' y el fin del cuerpo vuelven
        directo a la condición."""
        self.assertEqual(self.lineas_tac(
            "var m: integer = 0;\n"
            "for (m = 0; m < 2; ) {\n"
            "  m = m + 1;\n"
            "}"),
            ["global+0 = 0",
             "global+0 = 0",
             "L1_for_inicio:",
             "t1 = global+0 < 2",
             "ifFalse t1 goto L2_for_fin",
             "t1 = global+0 + 1",
             "global+0 = t1",
             "goto L1_for_inicio",
             "L2_for_fin:"])


class TestForeach(BaseTACControl):

    def test_foreach_desarmado_en_ciclo_indexado(self):
        """El arreglo literal aún no se traduce; el
        desarme del ciclo ya funciona sobre su operando."""
        self.assertEqual(self.lineas_tac(
            "let nums: integer[] = [1, 2];\n"
            "foreach (n in nums) {\n"
            "  print(n);\n"
            "}"),
            ["# pendiente: arreglo literal",
             "global+0 = /*arreglo literal*/ [1,2]",
             "t1 = 0",
             "L1_foreach_inicio:",
             "t2 = length global+0",
             "t3 = t1 < t2",
             "ifFalse t3 goto L2_foreach_fin",
             "global+8 = global+0[t1]",
             "print global+8",
             "L3_foreach_paso:",
             "t1 = t1 + 1",
             "goto L1_foreach_inicio",
             "L2_foreach_fin:"])


class TestSwitch(BaseTACControl):

    def test_switch_con_default(self):
        self.assertEqual(self.lineas_tac(
            "let i: integer = 2;\n"
            "switch (i) {\n"
            "  case 1:\n"
            "    print(\"uno\");\n"
            "  default:\n"
            "    print(\"otro\");\n"
            "}"),
            ["global+0 = 2",
             "t1 = global+0 == 1",
             "ifFalse t1 goto L2_case_no",
             "print \"uno\"",
             "goto L1_switch_fin",
             "L2_case_no:",
             "print \"otro\"",
             "L1_switch_fin:"])

    def test_switch_sin_default(self):
        """El último 'no cuadró' cae directo al fin."""
        self.assertEqual(self.lineas_tac(
            "let i: integer = 2;\n"
            "switch (i) {\n"
            "  case 1:\n"
            "    print(\"uno\");\n"
            "  case 2:\n"
            "    print(\"dos\");\n"
            "}"),
            ["global+0 = 2",
             "t1 = global+0 == 1",
             "ifFalse t1 goto L2_case_no",
             "print \"uno\"",
             "goto L1_switch_fin",
             "L2_case_no:",
             "t1 = global+0 == 2",
             "ifFalse t1 goto L3_case_no",
             "print \"dos\"",
             "goto L1_switch_fin",
             "L3_case_no:",
             "L1_switch_fin:"])


class TestTryCatch(BaseTACControl):

    def test_try_catch(self):
        """El flujo normal salta por encima del catch: solo una
            excepción de tiempo de ejecución aterriza en L_catch."""
        self.assertEqual(self.lineas_tac(
            "try {\n"
            "  print(1);\n"
            "} catch (e) {\n"
            "  print(2);\n"
            "}"),
            ["print 1",
             "goto L2_try_fin",
             "L1_catch:",
             "print 2",
             "L2_try_fin:"])


class TestEstructura(BaseTACControl):

    def test_sin_saltos_huerfanos(self):
        """Todo salto debe tener su etiqueta, en todos los
        constructos de control."""
        self.sin_saltos_huerfanos(
            "let x: integer = 5;\n"
            "if (x > 3) {\n"
            "  print(x);\n"
            "} else {\n"
            "  print(0);\n"
            "}\n"
            "while (x > 0) {\n"
            "  x = x - 1;\n"
            "}\n"
            "do {\n"
            "  x = x + 1;\n"
            "} while (x < 3);\n"
            "for (let i: integer = 0; i < x; i = i + 1) {\n"
            "  if (i == 1) { continue; }\n"
            "  if (i == 2) { break; }\n"
            "}\n"
            "switch (x) {\n"
            "  case 1:\n"
            "    print(\"uno\");\n"
            "  default:\n"
            "    print(\"otro\");\n"
            "}\n"
            "try {\n"
            "  print(x);\n"
            "} catch (e) {\n"
            "  print(\"error\");\n"
            "}")
