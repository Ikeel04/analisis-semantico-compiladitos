"""
Tests del algoritmo de asignación y reciclaje de variables temporales.

Corre con: python -m unittest discover -s tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "intermediate"))

from tac import ProgramaTAC
from temporales import GeneradorEtiquetas, PoolTemporales


class TestAsignacion(unittest.TestCase):

    def setUp(self):
        self.pool = PoolTemporales()

    def test_los_temporales_se_numeran_desde_uno(self):
        self.assertEqual(self.pool.nuevo(), "t1")
        self.assertEqual(self.pool.nuevo(), "t2")
        self.assertEqual(self.pool.nuevo(), "t3")

    def test_sin_liberar_nunca_se_reutiliza(self):
        for _ in range(5):
            self.pool.nuevo()
        self.assertEqual(self.pool.creados, 5)
        self.assertEqual(self.pool.reutilizaciones, 0)

    def test_el_prefijo_es_configurable(self):
        pool = PoolTemporales(prefijo="tmp")
        self.assertEqual(pool.nuevo(), "tmp1")


class TestReciclaje(unittest.TestCase):

    def setUp(self):
        self.pool = PoolTemporales()

    def test_un_temporal_liberado_se_vuelve_a_entregar(self):
        primero = self.pool.nuevo()
        self.pool.liberar(primero)
        self.assertEqual(self.pool.nuevo(), primero)
        self.assertEqual(self.pool.creados, 1)

    def test_se_reutiliza_el_liberado_mas_reciente(self):
        """La bolsa es una pila: mantiene chico el conjunto de temporales vivos."""
        t1, t2 = self.pool.nuevo(), self.pool.nuevo()
        self.pool.liberar(t1)
        self.pool.liberar(t2)
        self.assertEqual(self.pool.nuevo(), t2)   # el último liberado
        self.assertEqual(self.pool.nuevo(), t1)

    def test_liberar_no_deja_el_temporal_ocupado(self):
        t1 = self.pool.nuevo()
        self.assertEqual(self.pool.vivos, 1)
        self.pool.liberar(t1)
        self.assertEqual(self.pool.vivos, 0)

    def test_temporal_para_libera_los_operandos_y_entrega_destino(self):
        izquierda, derecha = self.pool.nuevo(), self.pool.nuevo()
        destino = self.pool.temporal_para(izquierda, derecha)
        self.assertEqual(destino, izquierda)      # el resultado reusa el izquierdo
        self.assertEqual(self.pool.creados, 2)    # no inventó un tercero

    def test_el_destino_reusa_el_operando_izquierdo(self):
        """Libera de derecha a izquierda para que el TAC se lea `t1 = t1 op t2`."""
        programa = ProgramaTAC()
        izquierda, derecha = self.pool.nuevo(), self.pool.nuevo()
        destino = self.pool.temporal_para(izquierda, derecha)
        programa.emitir_binaria("*", izquierda, derecha, destino)
        self.assertEqual(programa.como_texto().strip(), "t1 = t1 * t2")

    def test_el_pico_registra_el_maximo_simultaneo(self):
        a, b, c = self.pool.nuevo(), self.pool.nuevo(), self.pool.nuevo()
        self.assertEqual(self.pool.pico, 3)
        self.pool.liberar(a); self.pool.liberar(b); self.pool.liberar(c)
        self.pool.nuevo()
        self.assertEqual(self.pool.pico, 3)       # el pico no baja


class TestCasosQueNoDebenReciclarse(unittest.TestCase):
    """El pool recibe cualquier operando sin filtrar: aquí van los que debe ignorar."""

    def setUp(self):
        self.pool = PoolTemporales()

    def test_liberar_una_variable_del_programa_no_hace_nada(self):
        self.assertFalse(self.pool.liberar("contador"))
        self.pool.nuevo()
        self.assertEqual(self.pool.nuevo(), "t2")   # la bolsa seguía vacía

    def test_liberar_un_literal_no_hace_nada(self):
        self.assertFalse(self.pool.liberar("42"))
        self.assertFalse(self.pool.liberar(None))

    def test_una_variable_que_empieza_con_t_no_es_temporal(self):
        """'total' empieza con 't' pero no es tN; reciclarla sería un desastre."""
        self.assertFalse(self.pool.es_temporal("total"))
        self.assertFalse(self.pool.es_temporal("t"))
        self.assertFalse(self.pool.es_temporal("t1a"))
        self.assertTrue(self.pool.es_temporal("t1"))
        self.assertTrue(self.pool.es_temporal("t42"))

    def test_la_doble_liberacion_se_ignora(self):
        """Liberar dos veces dejaría el nombre repetido en la bolsa y dos
        valores distintos terminarían escribiendo en el mismo lugar."""
        t1 = self.pool.nuevo()
        self.assertTrue(self.pool.liberar(t1))
        self.assertFalse(self.pool.liberar(t1))
        self.assertEqual(self.pool.nuevo(), t1)
        self.assertEqual(self.pool.nuevo(), "t2")   # no volvió a entregar t1

    def test_liberar_un_temporal_nunca_entregado_se_ignora(self):
        self.assertFalse(self.pool.liberar("t9"))


class TestTraduccionDeExpresiones(unittest.TestCase):
    """El algoritmo aplicado: se traduce una expresión real y se cuenta."""

    def traducir(self, pool, programa, arbol):
        """Traduce ('op', izq, der) o un nombre, emitiendo TAC."""
        if isinstance(arbol, str):
            return arbol
        op, izquierda, derecha = arbol
        a = self.traducir(pool, programa, izquierda)
        b = self.traducir(pool, programa, derecha)
        destino = pool.temporal_para(a, b)   # recicla antes de pedir el destino
        programa.emitir_binaria(op, a, b, destino)
        return destino

    def test_expresion_encadenada_usa_un_solo_temporal(self):
        """a + b + c + d: cada suma consume el parcial anterior."""
        pool, programa = PoolTemporales(), ProgramaTAC()
        arbol = ("+", ("+", ("+", "a", "b"), "c"), "d")
        self.traducir(pool, programa, arbol)

        self.assertEqual(pool.creados, 1)
        self.assertEqual(programa.como_texto(), "\n".join([
            "    t1 = a + b",
            "    t1 = t1 + c",
            "    t1 = t1 + d",
        ]))

    def test_expresion_con_subarboles_usa_dos_temporales(self):
        """(a + b) * (c + d) - (e + f): el árbol obliga a tener dos vivos."""
        pool, programa = PoolTemporales(), ProgramaTAC()
        arbol = ("-", ("*", ("+", "a", "b"), ("+", "c", "d")), ("+", "e", "f"))
        self.traducir(pool, programa, arbol)

        self.assertEqual(pool.creados, 2)
        self.assertEqual(pool.pico, 2)
        self.assertEqual(programa.como_texto(), "\n".join([
            "    t1 = a + b",
            "    t2 = c + d",
            "    t1 = t1 * t2",
            "    t2 = e + f",
            "    t1 = t1 - t2",
        ]))

    def test_sin_reciclaje_la_misma_expresion_gasta_el_doble(self):
        """Comparación contra la traducción ingenua, que nunca libera."""
        pool, programa = PoolTemporales(), ProgramaTAC()

        def ingenua(arbol):
            if isinstance(arbol, str):
                return arbol
            op, izquierda, derecha = arbol
            a, b = ingenua(izquierda), ingenua(derecha)
            destino = pool.nuevo()           # pide sin liberar nunca
            programa.emitir_binaria(op, a, b, destino)
            return destino

        ingenua(("-", ("*", ("+", "a", "b"), ("+", "c", "d")), ("+", "e", "f")))
        self.assertEqual(pool.creados, 5)    # contra los 2 del test anterior

    def test_las_estadisticas_reportan_el_ahorro(self):
        pool, programa = PoolTemporales(), ProgramaTAC()
        self.traducir(pool, programa,
                      ("-", ("*", ("+", "a", "b"), ("+", "c", "d")), ("+", "e", "f")))
        datos = pool.estadisticas()
        self.assertEqual(datos["temporales_pedidos"], 5)
        self.assertEqual(datos["nombres_creados"], 2)
        self.assertEqual(datos["reutilizaciones"], 3)
        self.assertEqual(datos["ahorro"], 3)
        self.assertEqual(datos["pico_simultaneo"], 2)

    def test_al_terminar_una_expresion_solo_queda_vivo_su_resultado(self):
        pool, programa = PoolTemporales(), ProgramaTAC()
        resultado = self.traducir(pool, programa, ("*", ("+", "a", "b"), ("+", "c", "d")))
        self.assertEqual(pool.vivos, 1)
        self.assertTrue(pool.es_temporal(resultado))


class TestReinicioPorFuncion(unittest.TestCase):

    def test_reiniciar_vuelve_a_empezar_desde_t1(self):
        pool = PoolTemporales()
        pool.nuevo(); pool.nuevo()
        pool.reiniciar()
        self.assertEqual(pool.nuevo(), "t1")
        self.assertEqual(pool.pico, 1)
        self.assertEqual(pool.vivos, 1)

    def test_reiniciar_limpia_las_estadisticas(self):
        pool = PoolTemporales()
        t1 = pool.nuevo(); pool.liberar(t1); pool.nuevo()
        self.assertEqual(pool.reutilizaciones, 1)
        pool.reiniciar()
        self.assertEqual(pool.estadisticas()["reutilizaciones"], 0)


class TestEtiquetas(unittest.TestCase):

    def setUp(self):
        self.etiquetas = GeneradorEtiquetas()

    def test_las_etiquetas_son_consecutivas(self):
        self.assertEqual(self.etiquetas.nueva(), "L1")
        self.assertEqual(self.etiquetas.nueva(), "L2")

    def test_la_pista_queda_como_sufijo_legible(self):
        self.assertEqual(self.etiquetas.nueva("fin_while"), "L1_fin_while")

    def test_las_etiquetas_nunca_se_repiten(self):
        """No se reciclan: una etiqueta es una posición del programa."""
        generadas = {self.etiquetas.nueva() for _ in range(100)}
        self.assertEqual(len(generadas), 100)

    def test_dos_etiquetas_con_la_misma_pista_siguen_siendo_distintas(self):
        primera = self.etiquetas.nueva("fin_if")
        segunda = self.etiquetas.nueva("fin_if")
        self.assertNotEqual(primera, segunda)


if __name__ == "__main__":
    unittest.main(verbosity=2)
