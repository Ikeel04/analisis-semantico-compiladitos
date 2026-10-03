"""
Tests de la representación del código intermedio: que cada instrucción se
guarde con la forma (op, arg1, arg2, resultado) y que se imprima en la sintaxis
que ve el usuario.

Corre con: python -m unittest discover -s tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "intermediate"))

import tac
from tac import Cuadruplo, ProgramaTAC


class TestFormaDelCuadruplo(unittest.TestCase):

    def test_siempre_tiene_cuatro_campos(self):
        c = Cuadruplo(tac.SALTAR, resultado="L1")
        self.assertEqual(c.como_tupla(), ("goto", "_", "_", "L1"))

    def test_los_campos_sin_usar_se_muestran_con_guion_bajo(self):
        c = Cuadruplo(tac.ASIGNAR, "5", None, "x")
        self.assertEqual(c.como_tupla(), ("=", "5", "_", "x"))

    def test_una_binaria_guarda_los_dos_operandos_y_el_destino(self):
        c = Cuadruplo(tac.SUMA, "a", "b", "t1")
        self.assertEqual(c.como_tupla(), ("+", "a", "b", "t1"))


class TestImpresion(unittest.TestCase):
    """Cada instrucción se imprime como la sintaxis acordada en el diseño."""

    def comprobar(self, cuadruplo, esperado):
        self.assertEqual(str(cuadruplo), esperado)

    def test_asignacion(self):
        self.comprobar(Cuadruplo(tac.ASIGNAR, "5", None, "x"), "x = 5")

    def test_operaciones_binarias(self):
        for op in ("+", "-", "*", "/", "%", "==", "!=", "<", "<=", ">", ">=", "&&", "||"):
            self.comprobar(Cuadruplo(op, "a", "b", "t1"), f"t1 = a {op} b")

    def test_operaciones_unarias(self):
        self.comprobar(Cuadruplo(tac.NEGATIVO, "x", None, "t1"), "t1 = -x")
        self.comprobar(Cuadruplo(tac.NEGACION, "x", None, "t1"), "t1 = !x")

    def test_etiquetas_y_saltos(self):
        self.comprobar(Cuadruplo(tac.ETIQUETA, "L1"), "L1:")
        self.comprobar(Cuadruplo(tac.SALTAR, resultado="L1"), "goto L1")
        self.comprobar(Cuadruplo(tac.SALTAR_SI, "t1", None, "L1"), "if t1 goto L1")
        self.comprobar(Cuadruplo(tac.SALTAR_SI_FALSO, "t1", None, "L1"),
                       "ifFalse t1 goto L1")

    def test_funciones(self):
        self.comprobar(Cuadruplo(tac.INICIO_FUNCION, "suma"), "function suma:")
        self.comprobar(Cuadruplo(tac.FIN_FUNCION, "suma"), "endfunction suma")
        self.comprobar(Cuadruplo(tac.PARAMETRO, "x"), "param x")
        self.comprobar(Cuadruplo(tac.LLAMAR, "suma", 2, "t1"), "t1 = call suma, 2")
        self.comprobar(Cuadruplo(tac.RETORNAR, "t1"), "return t1")

    def test_llamada_sin_resultado_no_imprime_asignacion(self):
        """Una función void se llama por su efecto, no por su valor."""
        self.comprobar(Cuadruplo(tac.LLAMAR, "imprimir", 1), "call imprimir, 1")

    def test_retorno_sin_valor(self):
        self.comprobar(Cuadruplo(tac.RETORNAR), "return")

    def test_arreglos(self):
        self.comprobar(Cuadruplo(tac.LEER_INDICE, "a", "i", "t1"), "t1 = a[i]")
        self.comprobar(Cuadruplo(tac.ESCRIBIR_INDICE, "i", "t1", "a"), "a[i] = t1")

    def test_objetos(self):
        self.comprobar(Cuadruplo(tac.NUEVO, "Perro", None, "t1"), "t1 = new Perro")
        self.comprobar(Cuadruplo(tac.LEER_CAMPO, "p", "nombre", "t1"), "t1 = p.nombre")
        self.comprobar(Cuadruplo(tac.ESCRIBIR_CAMPO, "nombre", "t1", "p"),
                       "p.nombre = t1")

    def test_comentario(self):
        self.comprobar(Cuadruplo(tac.COMENTARIO, "inicio del while"),
                       "# inicio del while")


class TestProgramaTAC(unittest.TestCase):

    def setUp(self):
        self.programa = ProgramaTAC()

    def test_un_programa_nuevo_esta_vacio(self):
        self.assertEqual(len(self.programa), 0)
        self.assertEqual(self.programa.como_texto(), "")

    def test_las_instrucciones_quedan_en_orden_de_emision(self):
        self.programa.emitir_asignacion("x", "1")
        self.programa.emitir_asignacion("y", "2")
        self.assertEqual([str(c) for c in self.programa], ["x = 1", "y = 2"])

    def test_emitir_devuelve_el_cuadruplo_para_poder_parchearlo(self):
        salto = self.programa.emitir_salto_si_falso("t1", None)
        self.assertIsNone(salto.resultado)
        self.programa.parchear(salto, "L5")
        self.assertEqual(str(salto), "ifFalse t1 goto L5")

    def test_las_etiquetas_van_al_margen_y_el_resto_indentado(self):
        self.programa.emitir_etiqueta("L1")
        self.programa.emitir_asignacion("x", "1")
        self.assertEqual(self.programa.como_texto(), "L1:\n    x = 1")

    def test_numerar_antepone_el_indice(self):
        self.programa.emitir_etiqueta("L1")
        self.programa.emitir_asignacion("x", "1")
        self.assertEqual(self.programa.como_texto(numerar=True),
                         "   0  L1:\n   1      x = 1")

    def test_se_puede_indexar_e_iterar(self):
        self.programa.emitir_asignacion("x", "1")
        self.assertEqual(str(self.programa[0]), "x = 1")
        self.assertEqual(len(list(self.programa)), 1)

    def test_filas_para_ide_traen_el_cuadruplo_y_el_texto(self):
        self.programa.emitir_binaria("+", "a", "b", "t1")
        fila = self.programa.filas_para_ide()[0]
        self.assertEqual(fila["#"], 0)
        self.assertEqual(fila["Operación"], "+")
        self.assertEqual(fila["Arg1"], "a")
        self.assertEqual(fila["Arg2"], "b")
        self.assertEqual(fila["Resultado"], "t1")
        self.assertEqual(fila["Instrucción"], "t1 = a + b")


class TestProgramaCompleto(unittest.TestCase):
    """Se arma a mano el TAC de un if/else y de una llamada, para comprobar
    que el juego de instrucciones alcanza para traducir el lenguaje."""

    def test_if_else(self):
        p = ProgramaTAC()
        p.emitir_binaria("<", "x", "0", "t1")
        p.emitir_salto_si_falso("t1", "L1_else")
        p.emitir_asignacion("y", "1")
        p.emitir_salto("L2_fin")
        p.emitir_etiqueta("L1_else")
        p.emitir_asignacion("y", "2")
        p.emitir_etiqueta("L2_fin")

        self.assertEqual(p.como_texto(), "\n".join([
            "    t1 = x < 0",
            "    ifFalse t1 goto L1_else",
            "    y = 1",
            "    goto L2_fin",
            "L1_else:",
            "    y = 2",
            "L2_fin:",
        ]))

    def test_declaracion_y_llamada_de_funcion(self):
        p = ProgramaTAC()
        p.emitir_inicio_funcion("suma")
        p.emitir_binaria("+", "a", "b", "t1")
        p.emitir_retorno("t1")
        p.emitir_fin_funcion("suma")
        p.emitir_parametro("2")
        p.emitir_parametro("3")
        p.emitir_llamada("suma", 2, "t1")

        self.assertEqual(p.como_texto(), "\n".join([
            "    function suma:",
            "    t1 = a + b",
            "    return t1",
            "    endfunction suma",
            "    param 2",
            "    param 3",
            "    t1 = call suma, 2",
        ]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
