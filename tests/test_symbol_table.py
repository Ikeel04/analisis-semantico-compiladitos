"""
Batería de tests de la tabla de símbolos y manejo de ámbitos.
Corre con: python3 -m pytest test_symbol_table.py -v
(o python3 -m unittest test_symbol_table.py -v)
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "semantic"))

from symbol_table import SymbolTable, SemanticError


class TestInsertarRecuperarActualizar(unittest.TestCase):

    def test_insertar_y_recuperar_variable(self):
        st = SymbolTable()
        st.insert("x", "variable", type_="integer")
        sym = st.lookup("x")
        self.assertIsNotNone(sym)
        self.assertEqual(sym.type, "integer")

    def test_recuperar_no_declarada_devuelve_none(self):
        st = SymbolTable()
        self.assertIsNone(st.lookup("no_existe"))

    def test_actualizar_tipo_de_simbolo_existente(self):
        st = SymbolTable()
        st.insert("y", "variable", type_=None)
        st.update("y", type_="boolean")
        self.assertEqual(st.lookup("y").type, "boolean")

    def test_actualizar_simbolo_inexistente_lanza_error(self):
        st = SymbolTable()
        with self.assertRaises(SemanticError):
            st.update("no_existe", type_="integer")

    def test_redeclaracion_en_mismo_ambito_lanza_error(self):
        st = SymbolTable()
        st.insert("z", "variable", type_="integer")
        with self.assertRaises(SemanticError):
            st.insert("z", "variable", type_="string")


class TestManejoDeAmbitos(unittest.TestCase):

    def test_variable_global_visible_dentro_de_funcion(self):
        st = SymbolTable()
        st.insert("global_var", "variable", type_="integer")
        st.enter_scope("function", name="miFuncion")
        self.assertIsNotNone(st.lookup("global_var"))
        st.exit_scope()

    def test_variable_local_no_visible_fuera_de_su_bloque(self):
        st = SymbolTable()
        st.enter_scope("block")
        st.insert("local_var", "variable", type_="integer")
        st.exit_scope()
        self.assertIsNone(st.lookup("local_var"))

    def test_shadowing_variable_local_no_pisa_la_global(self):
        st = SymbolTable()
        st.insert("n", "variable", type_="integer")
        st.enter_scope("block")
        st.insert("n", "variable", type_="string")  # sombra válida, ámbito distinto
        self.assertEqual(st.lookup("n").type, "string")
        st.exit_scope()
        self.assertEqual(st.lookup("n").type, "integer")

    def test_mismo_nombre_en_bloques_hermanos_es_valido(self):
        st = SymbolTable()
        st.enter_scope("block")
        st.insert("temp", "variable", type_="integer")
        st.exit_scope()

        st.enter_scope("block")
        # no debe lanzar error: es un scope distinto (hermano), no redeclaración
        st.insert("temp", "variable", type_="string")
        self.assertEqual(st.lookup("temp").type, "string")
        st.exit_scope()

    def test_nuevo_entorno_por_funcion_clase_y_bloque(self):
        st = SymbolTable()
        f = st.enter_scope("function", name="foo")
        self.assertEqual(f.kind, "function")
        st.exit_scope()

        c = st.enter_scope("class", name="Animal")
        self.assertEqual(c.kind, "class")
        st.exit_scope()

        b = st.enter_scope("block")
        self.assertEqual(b.kind, "block")
        st.exit_scope()

    def test_no_se_puede_salir_del_ambito_global(self):
        st = SymbolTable()
        with self.assertRaises(RuntimeError):
            st.exit_scope()

    def test_ambitos_anidados_multiples_niveles(self):
        st = SymbolTable()
        st.enter_scope("function", name="externa")
        st.insert("a", "parameter", type_="integer")
        st.enter_scope("block")  # if dentro de la función
        st.insert("b", "variable", type_="integer")
        st.enter_scope("block")  # while anidado dentro del if
        self.assertIsNotNone(st.lookup("a"))  # visible desde el nivel más profundo
        self.assertIsNotNone(st.lookup("b"))
        st.exit_scope()
        st.exit_scope()
        self.assertIsNone(st.lookup("b"))  # ya no visible al salir del bloque
        st.exit_scope()


if __name__ == "__main__":
    unittest.main(verbosity=2)
