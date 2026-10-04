"""
Tests de integración de la generación de código intermedio: la compuerta que
exige el enunciado y la asignación de direcciones sobre programas reales.

El CONTENIDO del TAC no se prueba aquí: traducir el árbol es la parte de las
Personas 2 y 3.

Corre con: python -m unittest discover -s tests -v
"""

import os
import sys
import unittest

_BASE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(_BASE, "..", "src", "compiler"))

from pipeline import analizar_codigo

RUTA_EJEMPLOS = os.path.join(_BASE, "..", "ejemplos")

VALIDO = """
const MAX: integer = 10;
function suma(a: integer, b: integer): integer {
  return a + b;
}
let total: integer = suma(1, 2);
"""


class BaseGeneracion(unittest.TestCase):

    def analizar(self, codigo):
        return analizar_codigo("test.cps", codigo)

    def leer_ejemplo(self, nombre):
        with open(os.path.join(RUTA_EJEMPLOS, nombre), encoding="utf-8") as fh:
            return fh.read()


class TestCompuertaDeGeneracion(BaseGeneracion):

    def test_un_programa_valido_genera_codigo_intermedio(self):
        resultado = self.analizar(VALIDO)
        self.assertTrue(resultado.es_valido, resultado.errores)
        self.assertTrue(resultado.genero_tac)
        self.assertIsNotNone(resultado.tac)

    def test_un_error_lexico_bloquea_la_generacion(self):
        resultado = self.analizar('let a: integer = 1 ~ 2;')
        self.assertFalse(resultado.es_valido)
        self.assertFalse(resultado.genero_tac)
        self.assertIsNone(resultado.tac)

    def test_un_error_sintactico_bloquea_la_generacion(self):
        resultado = self.analizar('let a: integer = ;')
        self.assertFalse(resultado.genero_tac)

    def test_un_error_semantico_bloquea_la_generacion(self):
        """El caso importante: el árbol está perfecto, el programa parsea, y
        aun así no se genera nada porque los tipos no cuadran."""
        resultado = self.analizar('let a: integer = "texto";')
        self.assertTrue(any(e.tipo == "Semántico" for e in resultado.errores))
        self.assertFalse(resultado.genero_tac)

    def test_un_solo_error_entre_muchos_aciertos_bloquea_todo(self):
        resultado = self.analizar(VALIDO + '\nlet malo: boolean = 42;')
        self.assertEqual(len(resultado.errores), 1)
        self.assertFalse(resultado.genero_tac)

    def test_cuando_la_compuerta_bloquea_no_queda_nada_del_tac(self):
        resultado = self.analizar('let a: integer = "texto";')
        self.assertEqual(resultado.tac_texto, "")
        self.assertEqual(resultado.tac_filas, [])
        self.assertEqual(resultado.temporales, {})
        self.assertIsNone(resultado.memoria)

    def test_las_direcciones_se_calculan_aunque_haya_errores(self):
        """No son código intermedio, son información de la tabla de símbolos:
        sirven para revisarla en el IDE aunque el programa no compile."""
        resultado = self.analizar('let n: integer = 1;\nlet malo: boolean = 42;')
        self.assertFalse(resultado.genero_tac)
        self.assertTrue(any("@global+" in fila["Símbolos"] for fila in resultado.ambitos))


class TestCompuertaSobreLosEjemplos(BaseGeneracion):
    """Los ejemplos del repo son la demostración: los válidos generan, el
    resto no, sin excepción."""

    VALIDOS = ("ok_baja.cps", "ok_media.cps", "ok_semantica.cps")
    CON_ERRORES = ("errores_lexicos_baja.cps", "errores_lexicos_media.cps",
                   "errores_mixtos_baja.cps", "errores_mixtos_media.cps",
                   "errores_semanticos_baja.cps", "errores_semanticos_media.cps",
                   "errores_sintacticos_baja.cps", "errores_sintacticos_media.cps")

    def test_los_ejemplos_validos_generan(self):
        for nombre in self.VALIDOS:
            with self.subTest(ejemplo=nombre):
                resultado = self.analizar(self.leer_ejemplo(nombre))
                self.assertTrue(resultado.genero_tac, resultado.errores)

    def test_los_ejemplos_con_errores_no_generan(self):
        for nombre in self.CON_ERRORES:
            with self.subTest(ejemplo=nombre):
                resultado = self.analizar(self.leer_ejemplo(nombre))
                self.assertFalse(resultado.genero_tac)


class TestMemoriaSobreProgramasReales(BaseGeneracion):

    def test_un_programa_valido_arma_los_registros_de_activacion(self):
        resultado = self.analizar(VALIDO)
        self.assertIn("suma", resultado.memoria.registros)
        registro = resultado.memoria.registros["suma"]
        self.assertEqual([s.name for s in registro.parametros], ["a", "b"])
        # 16 cabecera + 2 enteros + 1 temporal: al traducirse el
        # cuerpo ('return a + b') el pool de la función tuvo un
        # pico de 1 temporal, y salir_funcion lo reserva en el
        # marco con fijar_temporales(pico) (DISENO_TAC.md §5).
        self.assertEqual(registro.temporales, 1)
        self.assertEqual(registro.tamano_total, 32)

    def test_los_metodos_y_las_funciones_anidadas_tienen_marco_propio(self):
        resultado = self.analizar(self.leer_ejemplo("ok_semantica.cps"))
        registros = resultado.memoria.registros
        self.assertIn("factorial", registros)
        self.assertIn("contador", registros)
        self.assertIn("contador.interno", registros)      # función anidada
        self.assertIn("Empleado.sumar", registros)        # método
        self.assertIn("Empleado.constructor", registros)

    def test_el_layout_de_la_clase_suma_sus_atributos(self):
        resultado = self.analizar(self.leer_ejemplo("ok_semantica.cps"))
        # Empleado tiene nombre (string, 8b) y puntos (integer, 4b)
        self.assertEqual(resultado.memoria.clases["Empleado"], 12)

    def test_ningun_dato_se_queda_sin_direccion(self):
        """Una variable sin dirección sería imposible de traducir a TAC."""
        for nombre in ("ok_baja.cps", "ok_media.cps", "ok_semantica.cps"):
            with self.subTest(ejemplo=nombre):
                resultado = self.analizar(self.leer_ejemplo(nombre))
                sin_direccion = []

                def recorrer(scope):
                    for simbolo in scope.symbols.values():
                        if (simbolo.kind in ("variable", "constant", "parameter")
                                and simbolo.direccion is None):
                            sin_direccion.append(simbolo.name)
                    for hijo in scope.children:
                        recorrer(hijo)

                recorrer(resultado.tabla.global_scope)
                self.assertEqual(sin_direccion, [])

    def test_la_variable_de_un_for_de_nivel_superior_recibe_direccion(self):
        """Caso que se escapaba: los bloques sueltos del programa principal."""
        resultado = self.analizar(
            'let n: integer = 0;\n'
            'for (var j: integer = 0; j < 3; j = j + 1) { n = n + j; }')
        bloques = [h for h in resultado.tabla.global_scope.children if h.kind == "block"]
        self.assertTrue(bloques)
        self.assertIsNotNone(bloques[0].resolve_local("j").direccion)


class TestEstadisticasDeTemporales(BaseGeneracion):

    def test_un_programa_valido_reporta_las_metricas(self):
        resultado = self.analizar(VALIDO)
        self.assertIn("nombres_creados", resultado.temporales)
        self.assertIn("pico_simultaneo", resultado.temporales)


if __name__ == "__main__":
    unittest.main(verbosity=2)
