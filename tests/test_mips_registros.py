"""
Tests de la selección de registros: descriptores, getReg, desalojos, análisis
de vida y bloques básicos. No dependen del traductor: se arma el TAC a mano.

Corre con: python -m unittest discover -s tests -v
"""

import os
import sys
import unittest

_BASE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(_BASE, "..", "src", "intermediate"))
sys.path.insert(0, os.path.join(_BASE, "..", "src", "backend"))

import tac as T
from programa_mips import ProgramaMIPS
from registros import MEMORIA, AsignadorRegistros
from unidades import UnidadTAC, bloques_basicos, separar_unidades
from vida import InfoVida


def ubicacion(nombre):
    return (f"[{nombre}]", False)


def siempre_vivo(nombre, pos):
    return True


def nunca_vivo(nombre, pos):
    return False


class TestDescriptores(unittest.TestCase):

    def setUp(self):
        self.programa = ProgramaMIPS()
        self.asignador = AsignadorRegistros(self.programa, ubicacion,
                                            registros=("$t0", "$t1", "$t2"))

    def ops(self):
        return [i.op for i in self.programa.texto]

    def test_leer_carga_una_vez(self):
        r1 = self.asignador.leer("global+0", 0, siempre_vivo)
        r2 = self.asignador.leer("global+0", 1, siempre_vivo)
        self.assertEqual(r1, r2)
        self.assertEqual(self.ops(), ["lw"])
        self.assertEqual(self.asignador.estadisticas["aciertos"], 1)

    def test_valor_cargado_esta_en_registro_y_memoria(self):
        r = self.asignador.leer("t1", 0, siempre_vivo)
        self.assertEqual(self.asignador.ubicaciones("t1"), {r, MEMORIA})

    def test_escribir_deja_el_valor_sucio(self):
        self.asignador.escribir("t1", "$t0")
        self.assertFalse(self.asignador.en_memoria("t1"))
        self.assertIn("t1*", self.asignador.instantanea())

    def test_reutiliza_el_registro_del_operando_que_muere(self):
        r = self.asignador.leer("t1", 0, siempre_vivo)
        destino = self.asignador.para_resultado("t2", [("t1", r)], 0, nunca_vivo)
        self.assertEqual(destino, r)

    def test_x_igual_x_mas_uno_reutiliza_su_registro(self):
        r = self.asignador.leer("global+0", 0, siempre_vivo)
        destino = self.asignador.para_resultado("global+0", [("global+0", r)], 0,
                                                siempre_vivo)
        self.assertEqual(destino, r)

    def test_operando_vivo_no_se_pisa_si_hay_libres(self):
        r = self.asignador.leer("global+0", 0, siempre_vivo)
        destino = self.asignador.para_resultado("t1", [("global+0", r)], 0,
                                                siempre_vivo)
        self.assertNotEqual(destino, r)

    def test_copia_comparte_registro(self):
        r = self.asignador.leer("t1", 0, siempre_vivo)
        self.asignador.copiar("global+0", r)
        self.assertEqual(self.asignador.registros[r], {"t1", "global+0"})
        self.assertEqual(self.asignador.registro_de("global+0"), r)
        self.assertEqual(self.ops(), ["lw"])   # la copia no emite nada

    def test_desalojo_guarda_solo_lo_sucio_y_vivo(self):
        for i, r in enumerate(("$t0", "$t1", "$t2")):
            self.asignador.escribir(f"t{i + 1}", r)
        # Los tres están sucios: elegir un registro obliga a guardar uno.
        self.asignador.leer("global+0", 0, siempre_vivo)
        self.assertIn("sw", self.ops())
        self.assertEqual(self.asignador.estadisticas["desalojos"], 1)

    def test_desalojo_prefiere_el_que_no_cuesta(self):
        self.asignador.escribir("t1", "$t0")
        self.asignador.escribir("t2", "$t1")
        self.asignador.leer("global+0", 0, siempre_vivo)   # $t2, limpio
        self.asignador.leer("global+4", 1, siempre_vivo)
        # Desaloja global+0 (está en memoria) sin emitir sw.
        self.assertNotIn("sw", self.ops())

    def test_muertos_se_desalojan_sin_guardar(self):
        for i, r in enumerate(("$t0", "$t1", "$t2")):
            self.asignador.escribir(f"t{i + 1}", r)
        self.asignador.leer("global+0", 0, nunca_vivo)
        self.assertNotIn("sw", self.ops())

    def test_protegidos_no_se_desalojan(self):
        for i, r in enumerate(("$t0", "$t1", "$t2")):
            self.asignador.escribir(f"t{i + 1}", r)
        r = self.asignador.leer("global+0", 0, nunca_vivo,
                                protegidos={"$t0", "$t1"})
        self.assertEqual(r, "$t2")

    def test_guardar_sucios_respeta_el_filtro(self):
        self.asignador.escribir("t1", "$t0")
        self.asignador.escribir("global+0", "$t1")
        self.asignador.guardar_sucios(lambda n: not n.startswith("t"))
        self.assertEqual(len([o for o in self.ops() if o == "sw"]), 1)
        self.assertTrue(self.asignador.en_memoria("global+0"))

    def test_byte_usa_sb_y_lbu(self):
        programa = ProgramaMIPS()
        asignador = AsignadorRegistros(programa, lambda n: ("0($s7)", True))
        asignador.leer("global+0", 0, siempre_vivo)
        asignador.escribir("global+0", "$t1")
        asignador.guardar_sucios(lambda n: True)
        self.assertEqual([i.op for i in programa.texto], ["lbu", "sb"])

    def test_olvidar_e_invalidar(self):
        self.asignador.escribir("t1", "$t0")
        self.asignador.olvidar("t1")
        self.assertEqual(self.asignador.instantanea(), "(vacío)")
        self.asignador.escribir("t2", "$t1")
        self.asignador.invalidar()
        self.assertIsNone(self.asignador.registro_de("t2"))


def unidad(*cuadruplos):
    u = UnidadTAC("main")
    u.instrucciones = list(enumerate(cuadruplos))
    return u


C = T.Cuadruplo


class TestBloquesYVida(unittest.TestCase):

    def test_separar_unidades_con_funcion_anidada(self):
        programa = T.ProgramaTAC()
        programa.emitir_inicio_funcion("f")
        programa.emitir_asignacion("fp+16", "1")
        programa.emitir_inicio_funcion("f.g")
        programa.emitir_retorno("2")
        programa.emitir_fin_funcion("f.g")
        programa.emitir_retorno("fp+16")
        programa.emitir_fin_funcion("f")
        programa.emitir_print("3")
        unidades = separar_unidades(programa)
        self.assertEqual([u.nombre for u in unidades], ["main", "f", "f.g"])
        self.assertEqual(len(unidades[1].instrucciones), 2)
        self.assertEqual(unidades[0].instrucciones[0][1].op, T.PRINT)

    def test_bloques_por_etiquetas_y_saltos(self):
        u = unidad(C("<", "global+0", "3", "t1"),
                   C("ifFalse", "t1", None, "L1"),
                   C("print", "1"),
                   C("label", "L1"),
                   C("print", "2"))
        bloques = bloques_basicos(u)
        self.assertEqual([b.posiciones for b in bloques], [[0, 1], [2], [3, 4]])
        self.assertEqual(bloques[0].sucesores, [2, 1])
        self.assertEqual(bloques[1].sucesores, [2])

    def test_temporal_vivo_a_traves_de_un_salto(self):
        # t1 se define antes del ciclo y se lee dentro: vive al salir del bloque 0.
        u = unidad(C("=", "0", None, "t1"),
                   C("label", "L1"),
                   C("<", "t1", "3", "t2"),
                   C("ifFalse", "t2", None, "L2"),
                   C("+", "t1", "1", "t1"),
                   C("goto", None, None, "L1"),
                   C("label", "L2"))
        vida = InfoVida(u)
        self.assertIn("t1", vida.vivos_al_salir(0))
        self.assertIn("t1", vida.vivos_al_salir(4))      # vuelve al inicio
        self.assertNotIn("t2", vida.vivos_al_salir(2))   # se consume en el ifFalse
        self.assertFalse(vida.vivo_despues("t2", 3))

    def test_temporal_muerto_tras_su_ultimo_uso(self):
        u = unidad(C("+", "global+0", "1", "t1"),
                   C("=", "t1", None, "global+4"),
                   C("print", "global+4"))
        vida = InfoVida(u)
        self.assertTrue(vida.vivo_despues("t1", 0))
        self.assertFalse(vida.vivo_despues("t1", 1))
        self.assertTrue(vida.vivo_despues("global+4", 2))   # variables: siempre

    def test_escritura_indexada_lee_el_arreglo(self):
        u = unidad(C("newarray", "2", None, "t1"),
                   C("[]=", "0", "5", "t1"),
                   C("=", "t1", None, "global+0"))
        vida = InfoVida(u)
        self.assertTrue(vida.vivo_despues("t1", 1))


if __name__ == "__main__":
    unittest.main()
