"""
Tests de las nuevas funcionalidades de la tabla de símbolos: direcciones de
memoria y registros de activación.

Corre con: python -m unittest discover -s tests -v
"""

import os
import sys
import unittest

_BASE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(_BASE, "..", "src", "intermediate"))
sys.path.insert(0, os.path.join(_BASE, "..", "src", "semantic"))

import memoria
from memoria import (INICIO_PARAMETROS, RegistroActivacion, alinear,
                     asignar_direcciones, tamano_de)
from symbol_table import SymbolTable


class TestTamanos(unittest.TestCase):

    def test_tamanos_de_los_tipos_primitivos(self):
        self.assertEqual(tamano_de("integer"), 4)
        self.assertEqual(tamano_de("float"), 8)
        self.assertEqual(tamano_de("boolean"), 1)
        self.assertEqual(tamano_de("void"), 0)

    def test_las_cadenas_se_guardan_por_referencia(self):
        self.assertEqual(tamano_de("string"), memoria.TAMANO_REFERENCIA)

    def test_los_arreglos_se_guardan_por_referencia(self):
        self.assertEqual(tamano_de("integer[]"), memoria.TAMANO_REFERENCIA)
        self.assertEqual(tamano_de("integer[][]"), memoria.TAMANO_REFERENCIA)

    def test_los_objetos_se_guardan_por_referencia(self):
        self.assertEqual(tamano_de("Perro"), memoria.TAMANO_REFERENCIA)

    def test_un_tipo_sin_resolver_reserva_una_referencia(self):
        """Si el análisis no pudo inferir el tipo, igual hay que reservar algo
        para no desalinear el resto del marco."""
        self.assertEqual(tamano_de(None), memoria.TAMANO_REFERENCIA)


class TestAlineacion(unittest.TestCase):

    def test_un_dato_de_un_byte_cabe_en_cualquier_lado(self):
        self.assertEqual(alinear(3, 1), 3)

    def test_un_entero_se_alinea_a_cuatro(self):
        self.assertEqual(alinear(1, 4), 4)
        self.assertEqual(alinear(4, 4), 4)
        self.assertEqual(alinear(5, 4), 8)

    def test_un_float_se_alinea_a_ocho(self):
        self.assertEqual(alinear(1, 8), 8)
        self.assertEqual(alinear(8, 8), 8)

    def test_la_alineacion_maxima_es_una_palabra(self):
        self.assertEqual(alinear(8, 16), 8)


class TestVariablesGlobales(unittest.TestCase):

    def setUp(self):
        self.tabla = SymbolTable()

    def test_las_globales_se_numeran_desde_cero(self):
        self.tabla.insert("a", "variable", "integer")
        self.tabla.insert("b", "variable", "integer")
        resumen = asignar_direcciones(self.tabla)

        self.assertEqual(self.tabla.lookup("a").direccion, "global+0")
        self.assertEqual(self.tabla.lookup("b").direccion, "global+4")
        self.assertEqual(resumen.tamano_global, 8)

    def test_se_deja_relleno_para_alinear(self):
        """boolean (1 byte) seguido de integer (4): el entero salta a +4."""
        self.tabla.insert("flag", "variable", "boolean")
        self.tabla.insert("n", "variable", "integer")
        resumen = asignar_direcciones(self.tabla)

        self.assertEqual(self.tabla.lookup("flag").offset, 0)
        self.assertEqual(self.tabla.lookup("n").offset, 4)
        self.assertEqual(resumen.tamano_global, 8)

    def test_las_constantes_tambien_ocupan_memoria(self):
        self.tabla.insert("MAX", "constant", "integer")
        asignar_direcciones(self.tabla)
        self.assertEqual(self.tabla.lookup("MAX").area, memoria.AREA_GLOBAL)

    def test_las_funciones_y_clases_no_reciben_direccion_de_dato(self):
        """Su 'dirección' es una etiqueta del código, no una celda de datos."""
        self.tabla.insert("f", "function", "integer", params=[])
        self.tabla.insert("Perro", "class", "Perro", parent=None)
        asignar_direcciones(self.tabla)

        self.assertIsNone(self.tabla.lookup("f").direccion)
        self.assertIsNone(self.tabla.lookup("Perro").direccion)

    def test_las_variables_de_un_bloque_suelto_viven_en_el_area_global(self):
        """El cuerpo de un for de nivel superior no abre un marco de pila."""
        self.tabla.insert("n", "variable", "integer")
        self.tabla.enter_scope("block")
        self.tabla.insert("j", "variable", "integer")
        self.tabla.exit_scope()
        resumen = asignar_direcciones(self.tabla)

        bloque = self.tabla.global_scope.children[0]
        self.assertEqual(bloque.resolve_local("j").area, memoria.AREA_GLOBAL)
        self.assertEqual(bloque.resolve_local("j").offset, 4)
        self.assertEqual(resumen.tamano_global, 8)


class TestRegistroDeActivacion(unittest.TestCase):

    def construir(self, parametros=(), locales=()):
        tabla = SymbolTable()
        tabla.insert("f", "function", "integer", params=list(parametros))
        tabla.enter_scope("function", name="f")
        for nombre, tipo in parametros:
            tabla.insert(nombre, "parameter", tipo)
        for nombre, tipo in locales:
            tabla.insert(nombre, "variable", tipo)
        tabla.exit_scope()
        return tabla, asignar_direcciones(tabla)

    def test_el_marco_reserva_el_enlace_y_la_direccion_de_retorno(self):
        _, resumen = self.construir()
        registro = resumen.registros["f"]
        self.assertEqual(INICIO_PARAMETROS, 16)
        self.assertEqual(registro.tamano_total, 16)

    def test_los_parametros_empiezan_despues_de_la_cabecera(self):
        tabla, resumen = self.construir(parametros=[("a", "integer"), ("b", "integer")])
        scope = tabla.global_scope.children[0]

        self.assertEqual(scope.resolve_local("a").direccion, "fp+16")
        self.assertEqual(scope.resolve_local("b").direccion, "fp+20")
        self.assertEqual(resumen.registros["f"].tamano_parametros, 8)

    def test_las_locales_van_despues_de_los_parametros(self):
        tabla, resumen = self.construir(parametros=[("a", "integer")],
                                        locales=[("x", "integer")])
        scope = tabla.global_scope.children[0]
        registro = resumen.registros["f"]

        self.assertEqual(scope.resolve_local("a").offset, 16)
        self.assertEqual(scope.resolve_local("x").offset, 20)
        self.assertEqual(registro.offset_locales, 20)
        self.assertEqual(registro.tamano_locales, 4)
        self.assertEqual(registro.tamano_total, 24)

    def test_los_parametros_quedan_en_orden_de_declaracion(self):
        _, resumen = self.construir(parametros=[("a", "integer"), ("b", "string"),
                                                ("c", "boolean")])
        nombres = [s.name for s in resumen.registros["f"].parametros]
        self.assertEqual(nombres, ["a", "b", "c"])

    def test_el_registro_queda_colgado_de_su_ambito(self):
        tabla, _ = self.construir(parametros=[("a", "integer")])
        scope = tabla.global_scope.children[0]
        self.assertIsNotNone(scope.registro)
        self.assertEqual(scope.registro.nombre, "f")

    def test_las_variables_de_un_bloque_viven_en_el_marco_de_su_funcion(self):
        tabla = SymbolTable()
        tabla.insert("f", "function", "integer", params=[])
        tabla.enter_scope("function", name="f")
        tabla.insert("x", "variable", "integer")
        tabla.enter_scope("block")
        tabla.insert("y", "variable", "integer")
        tabla.exit_scope()
        tabla.exit_scope()
        resumen = asignar_direcciones(tabla)

        registro = resumen.registros["f"]
        self.assertEqual([s.name for s in registro.locales], ["x", "y"])
        self.assertEqual(registro.tamano_locales, 8)

    def test_los_temporales_se_reservan_al_final(self):
        _, resumen = self.construir(parametros=[("a", "integer")])
        registro = resumen.registros["f"]
        self.assertEqual(registro.tamano_total, 20)

        registro.fijar_temporales(3)
        self.assertEqual(registro.temporales, 3)
        self.assertEqual(registro.offset_temporales, 20)
        self.assertEqual(registro.tamano_total, 20 + 3 * memoria.TAMANO_PALABRA)

    def test_describe_muestra_la_disposicion_del_marco(self):
        _, resumen = self.construir(parametros=[("a", "integer")],
                                    locales=[("x", "integer")])
        texto = resumen.registros["f"].describe()
        self.assertIn("enlace de control", texto)
        self.assertIn("dirección de retorno", texto)
        self.assertIn("fp+16   a (parámetro", texto)
        self.assertIn("fp+20   x (variable", texto)


class TestFuncionesAnidadasYMetodos(unittest.TestCase):

    def test_una_funcion_anidada_tiene_su_propio_marco(self):
        tabla = SymbolTable()
        tabla.insert("externa", "function", "integer", params=[])
        tabla.enter_scope("function", name="externa")
        tabla.insert("base", "variable", "integer")
        tabla.insert("interna", "function", "integer", params=[])
        tabla.enter_scope("function", name="interna")
        tabla.insert("x", "parameter", "integer")
        tabla.exit_scope()
        tabla.exit_scope()
        resumen = asignar_direcciones(tabla)

        self.assertIn("externa", resumen.registros)
        self.assertIn("externa.interna", resumen.registros)
        # 'base' es local de la externa, no de la interna
        self.assertEqual([s.name for s in resumen.registros["externa"].locales], ["base"])
        self.assertEqual(resumen.registros["externa.interna"].locales, [])

    def test_los_metodos_se_nombran_con_su_clase(self):
        tabla = SymbolTable()
        tabla.insert("Perro", "class", "Perro", parent=None)
        tabla.enter_scope("class", name="Perro")
        tabla.insert("ladrar", "function", "void", params=[])
        tabla.enter_scope("function", name="ladrar")
        tabla.exit_scope()
        tabla.exit_scope()
        resumen = asignar_direcciones(tabla)

        self.assertIn("Perro.ladrar", resumen.registros)

    def test_la_recursion_no_necesita_un_marco_distinto_por_llamada(self):
        """Hay UN registro de activación por función (el molde); cada llamada
        instancia uno en la pila, por eso dos activaciones no se pisan."""
        tabla = SymbolTable()
        tabla.insert("factorial", "function", "integer", params=[("n", "integer")])
        tabla.enter_scope("function", name="factorial")
        tabla.insert("n", "parameter", "integer")
        tabla.exit_scope()
        resumen = asignar_direcciones(tabla)

        self.assertEqual(len(resumen.registros), 1)
        self.assertEqual(resumen.registros["factorial"].tamano_total, 20)


class TestLayoutDeObjetos(unittest.TestCase):

    def declarar_clase(self, tabla, nombre, atributos, padre=None):
        tabla.insert(nombre, "class", nombre, parent=padre)
        tabla.enter_scope("class", name=nombre)
        for attr, tipo in atributos:
            tabla.insert(attr, "variable", tipo)
        tabla.exit_scope()

    def test_los_atributos_empiezan_en_cero(self):
        tabla = SymbolTable()
        self.declarar_clase(tabla, "Punto", [("x", "integer"), ("y", "integer")])
        resumen = asignar_direcciones(tabla)

        scope = tabla.global_scope.children[0]
        self.assertEqual(scope.resolve_local("x").direccion, "obj+0")
        self.assertEqual(scope.resolve_local("y").direccion, "obj+4")
        self.assertEqual(resumen.clases["Punto"], 8)

    def test_los_atributos_usan_el_area_de_objeto(self):
        tabla = SymbolTable()
        self.declarar_clase(tabla, "Punto", [("x", "integer")])
        asignar_direcciones(tabla)
        scope = tabla.global_scope.children[0]
        self.assertEqual(scope.resolve_local("x").area, memoria.AREA_ATRIBUTO)

    def test_los_heredados_van_primero(self):
        """Así una instancia de la subclase sirve donde se espera la base."""
        tabla = SymbolTable()
        self.declarar_clase(tabla, "Punto", [("x", "integer"), ("y", "integer")])
        self.declarar_clase(tabla, "Punto3D", [("z", "integer")], padre="Punto")
        resumen = asignar_direcciones(tabla)

        punto3d = [h for h in tabla.global_scope.children if h.name == "Punto3D"][0]
        self.assertEqual(punto3d.resolve_local("z").offset, 8)   # después de x, y
        self.assertEqual(resumen.clases["Punto3D"], 12)

    def test_la_herencia_de_varios_niveles_acumula(self):
        tabla = SymbolTable()
        self.declarar_clase(tabla, "A", [("a", "integer")])
        self.declarar_clase(tabla, "B", [("b", "integer")], padre="A")
        self.declarar_clase(tabla, "C", [("c", "integer")], padre="B")
        resumen = asignar_direcciones(tabla)

        self.assertEqual(resumen.clases["A"], 4)
        self.assertEqual(resumen.clases["B"], 8)
        self.assertEqual(resumen.clases["C"], 12)

    def test_una_herencia_circular_no_cuelga(self):
        """Caso fallido: el semántico ya lo rechaza, pero el layout no debe
        caer en recursión infinita si llega mal formado."""
        tabla = SymbolTable()
        self.declarar_clase(tabla, "A", [("a", "integer")], padre="B")
        self.declarar_clase(tabla, "B", [("b", "integer")], padre="A")
        resumen = asignar_direcciones(tabla)
        self.assertIn("A", resumen.clases)
        self.assertIn("B", resumen.clases)


class TestResumen(unittest.TestCase):

    def test_las_filas_del_ide_traen_global_clases_y_marcos(self):
        tabla = SymbolTable()
        tabla.insert("n", "variable", "integer")
        tabla.insert("Perro", "class", "Perro", parent=None)
        tabla.enter_scope("class", name="Perro")
        tabla.exit_scope()
        tabla.insert("f", "function", "void", params=[])
        tabla.enter_scope("function", name="f")
        tabla.exit_scope()
        resumen = asignar_direcciones(tabla)

        areas = [fila["Área"] for fila in resumen.filas_para_ide()]
        self.assertIn("global", areas)
        self.assertIn("objeto", areas)
        self.assertIn("marco", areas)


if __name__ == "__main__":
    unittest.main(verbosity=2)
