"""
Invariante de corrección del TAC: todo el código que se genera debe poder
ejecutarse. Se recorre el grafo de flujo y se exige que no queden
instrucciones inalcanzables (salvo un 'goto' muerto detrás de un 'return' u
otro salto, que es inofensivo: no hay optimización de mirilla).

Este test detecta justo la clase de error que una comparación línea por línea
no ve: un 'for' cuyo cuerpo nunca se ejecuta tiene un TAC bien formado.

Puntos de entrada: la primera instrucción, el cuerpo de cada función (se
alcanza con 'call', no cayendo desde la anterior) y cada etiqueta de 'catch'
(la alcanza una excepción, no el flujo normal).

Corre con: python -m unittest discover -s tests -v
"""

import glob
import os
import sys
import unittest

_BASE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(_BASE, "..", "src", "compiler"))
sys.path.insert(0, os.path.join(_BASE, "..", "src", "intermediate"))

from pipeline import analizar_codigo

RUTA_EJEMPLOS = os.path.join(_BASE, "..", "ejemplos")


def inalcanzables(programa) -> list[str]:
    """Instrucciones que ningún camino de ejecución puede alcanzar."""
    ins = list(programa)
    etiquetas = {c.arg1: i for i, c in enumerate(ins) if c.op == "label"}

    fin_de = {}                     # índice de 'function f' -> índice de su 'endfunction'
    for i, c in enumerate(ins):
        if c.op == "function":
            for j in range(i + 1, len(ins)):
                if ins[j].op == "endfunction" and ins[j].arg1 == c.arg1:
                    fin_de[i] = j
                    break

    entradas = [0] if ins else []
    entradas += [i + 1 for i in fin_de]
    entradas += [i for c, i in ((c, i) for i, c in enumerate(ins))
                 if c.op == "label" and "catch" in c.arg1]

    alcanzado, pendientes = set(), list(entradas)
    while pendientes:
        i = pendientes.pop()
        while 0 <= i < len(ins) and i not in alcanzado:
            alcanzado.add(i)
            c = ins[i]
            if c.op == "goto":
                i = etiquetas[c.resultado]
            elif c.op in ("if", "ifFalse"):
                pendientes.append(etiquetas[c.resultado])
                i += 1
            elif c.op in ("return", "endfunction"):
                break
            elif c.op == "function":
                i = fin_de[i] + 1      # el flujo de afuera salta el cuerpo
            else:
                i += 1

    muertas = []
    for i, c in enumerate(ins):
        if i in alcanzado:
            continue
        if c.op == "goto":             # salto muerto tras return/goto: inofensivo
            continue
        if c.op == "endfunction":      # marcador de fin: no es código ejecutable
            continue
        muertas.append(f"{i}: {c}")
    return muertas


class TestAlcanzabilidad(unittest.TestCase):

    def codigo(self, fuente):
        r = analizar_codigo("t.cps", fuente)
        self.assertTrue(r.es_valido, [str(e) for e in r.errores])
        return r.tac

    def assertTodoAlcanzable(self, fuente):
        self.assertEqual(inalcanzables(self.codigo(fuente)), [])

    def test_for_con_paso_ejecuta_su_cuerpo(self):
        self.assertTodoAlcanzable(
            "var s: integer = 0;\n"
            "for (let i: integer = 0; i < 3; i = i + 1) {\n"
            "  s = s + i;\n"
            "}")

    def test_for_sin_paso(self):
        self.assertTodoAlcanzable(
            "var m: integer = 0;\n"
            "for (m = 0; m < 2; ) {\n"
            "  m = m + 1;\n"
            "}")

    def test_for_con_break_y_continue(self):
        self.assertTodoAlcanzable(
            "var s: integer = 0;\n"
            "for (let i: integer = 0; i < 9; i = i + 1) {\n"
            "  if (i == 2) { continue; }\n"
            "  if (i == 5) { break; }\n"
            "  s = s + i;\n"
            "}")

    def test_while_do_while_y_foreach(self):
        self.assertTodoAlcanzable(
            "let n: integer = 3;\n"
            "let xs: integer[] = [1, 2];\n"
            "while (n > 0) { n = n - 1; }\n"
            "do { n = n + 1; } while (n < 3);\n"
            "foreach (x in xs) { n = n + x; }")

    def test_if_else_y_switch(self):
        self.assertTodoAlcanzable(
            "let n: integer = 1;\n"
            "if (n > 0) { n = 2; } else { n = 3; }\n"
            "switch (n) {\n"
            "  case 1: print(\"a\");\n"
            "  case 2: print(\"b\");\n"
            "  default: print(\"c\");\n"
            "}")

    def test_try_catch_alcanza_su_catch_como_entrada(self):
        self.assertTodoAlcanzable(
            "let xs: integer[] = [1];\n"
            "try { print(xs[5]); } catch (e) { print(\"x\"); }")

    def test_funciones_clases_y_atributos_inicializados(self):
        self.assertTodoAlcanzable(
            "class C {\n"
            "  var n: integer = 1;\n"
            "  function m(): integer { return this.n; }\n"
            "}\n"
            "function f(a: integer): integer { return a; }\n"
            "let c: C = new C();\n"
            "let r: integer = f(c.m());")

    def test_el_detector_encuentra_un_cuerpo_inalcanzable(self):
        """Prueba del propio detector: un TAC con el defecto original del
        'for' (sin salto al cuerpo) debe marcar el cuerpo como muerto."""
        from tac import ProgramaTAC
        p = ProgramaTAC()
        p.emitir_etiqueta("L1")
        p.emitir_binaria("<", "i", "3", "t1")
        p.emitir_salto_si_falso("t1", "L2")
        p.emitir_etiqueta("L3")             # paso: se cae directo desde la condición
        p.emitir_asignacion("i", "t1")
        p.emitir_salto("L1")
        p.emitir_etiqueta("L4")             # cuerpo: nadie salta aquí
        p.emitir_asignacion("s", "i")
        p.emitir_salto("L3")
        p.emitir_etiqueta("L2")
        muertas = inalcanzables(p)
        self.assertTrue(any("s = i" in m for m in muertas), muertas)


class TestAlcanzabilidadDeLosEjemplos(unittest.TestCase):

    def test_ningun_ejemplo_valido_tiene_codigo_inalcanzable(self):
        rutas = sorted(glob.glob(os.path.join(RUTA_EJEMPLOS, "ok_*.cps"))
                       + glob.glob(os.path.join(RUTA_EJEMPLOS, "tac_*.cps")))
        self.assertGreater(len(rutas), 0)
        for ruta in rutas:
            with self.subTest(ejemplo=os.path.basename(ruta)):
                with open(ruta, encoding="utf-8") as f:
                    r = analizar_codigo(os.path.basename(ruta), f.read())
                self.assertTrue(r.genero_tac)
                self.assertEqual(inalcanzables(r.tac), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
