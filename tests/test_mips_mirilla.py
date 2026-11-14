"""
Tests del optimizador de mirilla: cada regla por separado, sobre listas de
instrucciones armadas a mano, y su efecto sobre programas completos.

Corre con: python -m unittest discover -s tests -v
"""

import os
import sys
import unittest

_BASE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(_BASE, "..", "src", "compiler"))
sys.path.insert(0, os.path.join(_BASE, "..", "src", "backend"))

from mirilla import OptimizadorMirilla
from programa_mips import Instr

from test_mips_traductor import MARS_JAR, compilar, ejecutar_en_mars


def I(op, *args):
    return Instr(op, tuple(str(a) for a in args))


def L(nombre):
    return Instr("label", (nombre,))


def texto(lista):
    return [str(i).strip() for i in lista if not i.es_comentario]


class TestReglas(unittest.TestCase):

    def optimizar(self, *instrucciones):
        lista, aplicadas = OptimizadorMirilla().optimizar(list(instrucciones))
        return texto(lista), aplicadas

    def test_movimiento_redundante(self):
        salida, aplicadas = self.optimizar(I("move", "$t0", "$t0"), I("jr", "$ra"))
        self.assertEqual(salida, ["jr      $ra"])
        self.assertEqual(aplicadas["Movimiento redundante"], 1)

    def test_carga_tras_almacenamiento_mismo_registro(self):
        salida, aplicadas = self.optimizar(I("sw", "$t0", "8($fp)"), I("lw", "$t0", "8($fp)"))
        self.assertEqual(salida, ["sw      $t0, 8($fp)"])
        self.assertEqual(aplicadas["Carga tras almacenamiento"], 1)

    def test_carga_tras_almacenamiento_otro_registro(self):
        salida, _ = self.optimizar(I("sw", "$t0", "8($fp)"), I("lw", "$t1", "8($fp)"))
        self.assertEqual(salida[1].split("#")[0].strip(), "move    $t1, $t0")

    def test_carga_tras_almacenamiento_no_cruza_etiquetas(self):
        salida, _ = self.optimizar(I("sw", "$t0", "8($fp)"), L("fn_f"),
                                   I("lw", "$t0", "8($fp)"))
        self.assertEqual(len(salida), 3)

    def test_almacenamiento_redundante(self):
        salida, aplicadas = self.optimizar(I("lw", "$t0", "8($fp)"), I("sw", "$t0", "8($fp)"))
        self.assertEqual(salida, ["lw      $t0, 8($fp)"])
        self.assertEqual(aplicadas["Almacenamiento redundante"], 1)

    def test_almacenamiento_con_base_pisada_no_se_quita(self):
        salida, _ = self.optimizar(I("lw", "$t0", "0($t0)"), I("sw", "$t0", "0($t0)"))
        self.assertEqual(len(salida), 2)

    def test_identidades_algebraicas(self):
        salida, aplicadas = self.optimizar(
            I("addiu", "$t0", "$t1", 0), I("mul", "$t2", "$t3", 1),
            I("addu", "$t4", "$zero", "$t5"), I("mul", "$t6", "$t7", 0))
        self.assertTrue(salida[0].startswith("move    $t0, $t1"))
        self.assertTrue(salida[1].startswith("move    $t2, $t3"))
        self.assertTrue(salida[2].startswith("move    $t4, $t5"))
        self.assertTrue(salida[3].startswith("li      $t6, 0"))
        self.assertEqual(aplicadas["Identidades algebraicas"], 4)

    def test_reduccion_de_fuerza(self):
        salida, aplicadas = self.optimizar(I("mul", "$t0", "$t1", 8), I("mul", "$t2", "$t3", 6))
        self.assertTrue(salida[0].startswith("sll     $t0, $t1, 3"))
        self.assertTrue(salida[1].startswith("mul     $t2, $t3, 6"))
        self.assertEqual(aplicadas["Reducción de fuerza"], 1)

    def test_fusion_de_ajustes_de_pila(self):
        salida, aplicadas = self.optimizar(
            I("addiu", "$sp", "$sp", -4), I("sw", "$t0", "0($sp)"),
            I("addiu", "$sp", "$sp", -4), I("sw", "$t1", "0($sp)"),
            I("jal", "fn_f"))
        self.assertEqual(salida[:3], ["addiu   $sp, $sp, -8",
                                      "sw      $t0, 4($sp)",
                                      "sw      $t1, 0($sp)"])
        self.assertEqual(aplicadas["Fusión de ajustes de pila"], 1)

    def test_fusion_con_instrucciones_que_no_usan_sp(self):
        salida, _ = self.optimizar(
            I("li", "$a2", 5), I("addiu", "$sp", "$sp", -4), I("sw", "$a2", "0($sp)"),
            I("li", "$a2", 6), I("addiu", "$sp", "$sp", -4), I("sw", "$a2", "0($sp)"),
            I("jal", "fn_f"))
        self.assertEqual(salida[:5], ["li      $a2, 5", "addiu   $sp, $sp, -8",
                                      "sw      $a2, 4($sp)", "li      $a2, 6",
                                      "sw      $a2, 0($sp)"])

    def test_fusion_no_cruza_llamadas_ni_otros_usos_de_sp(self):
        salida, _ = self.optimizar(
            I("addiu", "$sp", "$sp", -4), I("jal", "fn_f"), I("addiu", "$sp", "$sp", 4),
            I("addiu", "$sp", "$sp", -4), I("sb", "$t0", "0($sp)"),
            I("addiu", "$sp", "$sp", -4))
        # El +4 de después del jal y el -4 siguiente se anulan; el primer ajuste
        # no cruza el jal y el sb (no es sw/lw) corta la fusión del último.
        self.assertEqual(salida, ["addiu   $sp, $sp, -4", "jal     fn_f",
                                  "sb      $t0, 0($sp)", "addiu   $sp, $sp, -4"])

    def test_ajustes_que_se_anulan_desaparecen(self):
        salida, _ = self.optimizar(I("addiu", "$sp", "$sp", -8),
                                   I("addiu", "$sp", "$sp", 8), I("jr", "$ra"))
        self.assertEqual(salida, ["jr      $ra"])

    def test_codigo_inalcanzable(self):
        salida, aplicadas = self.optimizar(
            I("j", "fn_f_fin"), I("li", "$t0", 1), I("addu", "$t0", "$t0", "$t0"),
            L("fn_f_fin"), I("jr", "$ra"))
        self.assertNotIn("li      $t0, 1", salida)
        self.assertEqual(aplicadas["Código inalcanzable"], 2)

    def test_salto_a_siguiente(self):
        salida, aplicadas = self.optimizar(I("j", "fn_f_fin"), L("fn_f_fin"), I("jr", "$ra"))
        self.assertEqual(salida, ["fn_f_fin:", "jr      $ra"])
        self.assertEqual(aplicadas["Salto a la siguiente instrucción"], 1)

    def test_cadena_de_saltos(self):
        salida, aplicadas = self.optimizar(
            I("beqz", "$t0", "L1"), I("li", "$t1", 1), I("jr", "$ra"),
            L("L2"), I("li", "$t2", 2), I("jr", "$ra"),
            L("L1"), I("j", "L2"))
        self.assertEqual(salida[0], "beqz    $t0, L2")
        self.assertNotIn("L1:", salida)
        self.assertGreaterEqual(aplicadas["Cadena de saltos"], 1)

    def test_salto_sobre_salto(self):
        salida, aplicadas = self.optimizar(
            I("beqz", "$t0", "L1"), I("j", "L2"), L("L1"), I("li", "$t1", 1),
            L("L2"), I("jr", "$ra"))
        self.assertEqual(salida[0], "bnez    $t0, L2")
        self.assertNotIn("L1:", salida)      # quedó sin uso
        self.assertEqual(aplicadas["Salto sobre salto"], 1)

    def test_etiquetas_sin_uso_solo_internas(self):
        salida, aplicadas = self.optimizar(L("L7_if_fin"), L("fn_f"), L("main"),
                                           I("jr", "$ra"))
        self.assertEqual(salida, ["fn_f:", "main:", "jr      $ra"])
        self.assertEqual(aplicadas["Etiquetas sin uso"], 1)

    def test_hay_al_menos_seis_transformaciones(self):
        self.assertGreaterEqual(len(OptimizadorMirilla().reglas), 6)


class TestSobreProgramas(unittest.TestCase):

    CODIGO = """
    function f(a: integer, b: integer, c: integer): integer {
      return a * 4 + b * 1 + c;
    }
    print(f(1, 2, 3));
    """

    def test_reduce_instrucciones(self):
        resultado = compilar(self.CODIGO)
        self.assertLess(resultado.instrucciones_despues, resultado.instrucciones_antes)
        self.assertIn("sll", resultado.asm)
        self.assertNotIn("sll", resultado.asm_sin_optimizar)
        self.assertGreater(sum(resultado.mirilla.values()), 0)

    @unittest.skipUnless(MARS_JAR, "requiere MARS_JAR y Java")
    def test_misma_salida_antes_y_despues(self):
        resultado = compilar(self.CODIGO)
        self.assertEqual(ejecutar_en_mars(resultado.asm),
                         ejecutar_en_mars(resultado.asm_sin_optimizar))
        self.assertEqual(ejecutar_en_mars(resultado.asm), "9")


if __name__ == "__main__":
    unittest.main()
