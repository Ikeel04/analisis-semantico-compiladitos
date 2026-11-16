"""
Tests de la parte 3 del backend MIPS (src/backend/datos.py): arreglos, clases
y objetos, herencia y cadenas en tiempo de ejecución.

Hay tres tipos de prueba:
- estructura: qué instrucciones se generan (sin MARS);
- casos exitosos: la salida de MARS es la del intérprete del TAC;
- casos fallidos: índices fuera de rango, arreglos y objetos null, atrapados
  con try/catch o no atrapados (el programa imprime el error y termina).

Los que ejecutan MARS necesitan MARS_JAR (ver test_mips_traductor.py).

Corre con: python -m unittest discover -s tests -v
"""

import unittest

from test_mips_traductor import MARS_JAR, compilar, ejecutar_en_mars

from pipeline import analizar_codigo

import datos as D
from programa_mips import ProgramaMIPS


def analizar(codigo):
    resultado = analizar_codigo("test.cps", codigo)
    assert resultado.genero_asm, [str(e) for e in resultado.errores]
    return resultado


def esperada(codigo):
    return "\n".join(analizar(codigo).ejecucion.salida)


def lineas(asm):
    return [l.split("#")[0].strip() for l in asm.splitlines()]


def rutina(asm, etiqueta):
    """Instrucciones de una rutina de soporte (hasta su `jr $ra`)."""
    texto = lineas(asm)
    inicio = texto.index(f"{etiqueta}:")
    fin = texto.index("jr      $ra", inicio)
    return texto[inicio:fin + 1]


CLASES = """
class Animal {
  var nombre: string;
  var vivo: boolean = true;
  var patas: integer = 4;
}
class Perro : Animal {
  var trucos: integer;
}
"""


# ----------------------------------------------------------------------
# Estructura
# ----------------------------------------------------------------------

class TestArreglos(unittest.TestCase):

    def test_newarray_reserva_longitud_mas_elementos(self):
        asm = lineas(compilar("let a: integer[] = [7, 8, 9];").asm_sin_optimizar)
        self.assertIn("li      $a0, 16", asm)            # 4 · (3 + 1)
        self.assertIn("li      $v0, 9", asm)             # sbrk
        self.assertIn("li      $a1, 3", asm)             # longitud en 0(p)

    def test_literal_recien_creado_no_verifica_limites(self):
        # t1 = newarray 3; t1[0] = 7 ... : el índice literal es menor que la
        # longitud conocida, no hace falta revisar null ni límites.
        asm = compilar("let a: integer[] = [7, 8, 9];").asm_sin_optimizar
        self.assertNotIn("__error_indice", "\n".join(
            l for l in lineas(asm) if l.startswith(("beqz", "bnez"))))
        for offset in (4, 8, 12):
            self.assertTrue(any(l.startswith("sw") and l.endswith(f"{offset}($t0)")
                                for l in lineas(asm)), offset)

    def test_indice_variable_verifica_null_y_limites(self):
        asm = lineas(compilar("""
            let a: integer[] = [1, 2];
            let i: integer = 1;
            print(a[i]);
        """).asm_sin_optimizar)
        self.assertTrue(any(l.startswith("beqz") and "__error_null" in l for l in asm))
        self.assertTrue(any(l.startswith("sltu") for l in asm))
        self.assertTrue(any(l.startswith("beqz") and "__error_indice" in l for l in asm))
        self.assertTrue(any(l.startswith("sll") and l.endswith(", 2") for l in asm))

    def test_length_lee_la_primera_palabra(self):
        asm = compilar("""
            let a: integer[] = [1, 2];
            foreach (x in a) { print(x); }
        """).asm_sin_optimizar
        self.assertIn("# length", asm)

    def test_sin_pendientes(self):
        resultado = compilar("""
            let m: integer[][] = [[1, 2], [3, 4]];
            m[0][1] = m[1][0];
            print(m);
        """)
        self.assertEqual(resultado.pendientes, [])


class TestObjetos(unittest.TestCase):

    def test_offsets_iguales_a_la_tabla_de_simbolos(self):
        resultado = analizar(CLASES + "let p: Perro = new Perro();")
        tipos = __import__("tipos").InferenciaTipos(resultado.tabla, resultado.memoria)
        atributos = D.construir_atributos(tipos)
        for scope in resultado.tabla.global_scope.children:
            if scope.kind != "class":
                continue
            for simbolo in scope.symbols.values():
                if simbolo.kind == "variable":
                    self.assertEqual(atributos[scope.name][simbolo.name][0], simbolo.offset)

    def test_heredados_primero(self):
        resultado = analizar(CLASES + "let p: Perro = new Perro();")
        tipos = __import__("tipos").InferenciaTipos(resultado.tabla, resultado.memoria)
        atributos = D.construir_atributos(tipos)
        for campo in ("nombre", "vivo", "patas"):
            self.assertEqual(atributos["Perro"][campo], atributos["Animal"][campo])
        self.assertGreater(atributos["Perro"]["trucos"][0], atributos["Animal"]["patas"][0])

    def test_new_reserva_el_tamano_de_la_clase(self):
        resultado = analizar(CLASES + "let p: Perro = new Perro();")
        tamano = resultado.memoria.clases["Perro"]
        self.assertIn(f"li      $a0, {(tamano + 3) // 4 * 4}",
                      lineas(resultado.ensamblador.asm_sin_optimizar))

    def test_boolean_de_un_byte(self):
        asm = lineas(compilar(CLASES + """
            let p: Perro = new Perro();
            p.vivo = false;
            print(p.vivo);
        """).asm_sin_optimizar)
        self.assertTrue(any(l.startswith("sb") for l in asm))
        self.assertTrue(any(l.startswith("lbu") for l in asm))

    def test_atributo_sin_this_usa_el_receptor(self):
        resultado = compilar("""
            class C {
              var n: integer;
              function inc() { n = n + 1; }
            }
            let c: C = new C();
            c.inc();
        """)
        marco = resultado.marcos["C.inc"]
        asm = lineas(resultado.asm_sin_optimizar)
        self.assertIn(f"lw      $a2, {marco.offset_receptor}($fp)", asm)
        self.assertIn(f"lw      $a1, {marco.offset_receptor}($fp)", asm)
        self.assertEqual(resultado.pendientes, [])

    def test_acceso_externo_verifica_null(self):
        asm = compilar(CLASES + """
            let p: Perro = new Perro();
            print(p.patas);
        """).asm_sin_optimizar
        self.assertIn("__error_objeto_null", asm)


class TestCadenas(unittest.TestCase):

    def test_concatenacion_llama_a_concat_una_rutina(self):
        asm = compilar('let a: string = "x"; let b: string = a + "y" + a;').asm_sin_optimizar
        self.assertIn("jal     __concat", asm)
        self.assertEqual(asm.count("__concat:"), 1)
        self.assertEqual(asm.count("__strlen:"), 1)

    def test_igualdad_de_cadenas_compara_contenido(self):
        asm = compilar('let a: string = "x"; print(a == "x"); print(a != "y");').asm
        self.assertIn("jal     __strcmp", asm)
        self.assertIn("xori", asm)                      # != es el negado

    def test_igualdad_de_enteros_sigue_siendo_seq(self):
        asm = compilar("let a: integer = 1; print(a == 2);").asm
        self.assertNotIn("__strcmp", asm)
        self.assertIn("seq", asm)


class TestRutinas(unittest.TestCase):
    """Las rutinas no pueden pisar registros del asignador ($t*, $s*) sin
    guardarlos, ni $v1 / $fp / $s7."""

    PROGRAMA = """
        let a: string = "x" + "y";
        print(a == "xy");
        let m: integer[][] = [[1], [2]];
        print(m);
    """

    def _escrituras(self, cuerpo):
        escritos = set()
        for l in cuerpo:
            partes = l.replace(",", " ").split()
            if len(partes) > 1 and not partes[0].startswith(("s", "b", "j")) \
                    and not partes[0].endswith(":"):
                escritos.add(partes[1])
        return escritos

    def test_rutinas_respetan_los_registros(self):
        asm = compilar(self.PROGRAMA).asm_sin_optimizar
        for nombre in (D.STRLEN, D.STRCMP):
            escritos = self._escrituras(rutina(asm, nombre))
            self.assertTrue(escritos <= {"$v0", "$a0", "$a1", "$a2", "$a3"},
                            (nombre, escritos))
        for nombre in (D.CONCAT, D.IMPRIMIR_ARREGLO):
            cuerpo = rutina(asm, nombre)
            self.assertNotIn("$v1", " ".join(cuerpo))
            # todo $t que se escribe se guardó antes en la pila
            for registro in self._escrituras(cuerpo):
                if registro.startswith("$t"):
                    self.assertTrue(any(l.startswith("sw") and registro in l
                                        for l in cuerpo), (nombre, registro))

    @unittest.skipUnless(MARS_JAR, "requiere MARS_JAR y Java")
    def test_int_a_cadena(self):
        # Compiscript no permite string + integer, pero la rutina queda lista
        # para el backend: se prueba sola, con un main escrito a mano.
        p = ProgramaMIPS()
        p.etiqueta("main")
        for valor in (0, 7, -45, 2147483647, -2147483648):
            p.emitir("li", "$a0", valor)
            p.emitir("jal", p.usar_rutina(D.INT_A_CADENA, D.rutina_int_a_cadena))
            p.emitir("move", "$a0", "$v0")
            p.emitir("li", "$v0", 4)
            p.emitir("syscall")
            p.emitir("li", "$a0", 10)
            p.emitir("li", "$v0", 11)
            p.emitir("syscall")
        p.emitir("li", "$v0", 10)
        p.emitir("syscall")
        p.emitir_rutinas()
        self.assertEqual(ejecutar_en_mars(p.como_texto()),
                         "0\n7\n-45\n2147483647\n-2147483648")


# ----------------------------------------------------------------------
# Casos exitosos en MARS
# ----------------------------------------------------------------------

@unittest.skipUnless(MARS_JAR, "requiere MARS_JAR y Java")
class TestMARSExitosos(unittest.TestCase):

    def comprobar(self, codigo):
        resultado = analizar(codigo)
        self.assertIsNone(resultado.ejecucion.error)
        esperado = "\n".join(resultado.ejecucion.salida)
        self.assertEqual(ejecutar_en_mars(resultado.ensamblador.asm), esperado)
        self.assertEqual(ejecutar_en_mars(resultado.ensamblador.asm_sin_optimizar), esperado)

    def test_arreglo_modificado_dentro_de_una_funcion(self):
        self.comprobar("""
            function duplicar(v: integer[]) {
              let i: integer = 0;
              while (i < 3) { v[i] = v[i] * 2; i = i + 1; }
            }
            let a: integer[] = [1, 2, 3];
            duplicar(a);
            print(a);
        """)

    def test_matriz_e_impresion(self):
        self.comprobar("""
            let m: integer[][] = [[1, 2], [3, 4]];
            m[0][1] = m[1][0] + m[1][1];
            print(m[0][1]);
            print(m);
            let s: string[] = ["a", "b"];
            print(s);
        """)

    def test_objeto_con_arreglo_y_herencia(self):
        self.comprobar("""
            class Base { var id: integer = 7; var ok: boolean = true; }
            class Hija : Base {
              var datos: integer[];
              function constructor() { this.datos = [1, 2, 3]; }
              function suma(): integer {
                let t: integer = this.id;
                foreach (x in datos) { t = t + x; }
                return t;
              }
            }
            let h: Hija = new Hija();
            print(h.suma());
            print(h.ok);
        """)

    def test_concatenacion_recursiva(self):
        self.comprobar("""
            function eco(s: string, n: integer): string {
              if (n == 0) { return s; }
              return eco(s + "!", n - 1);
            }
            print(eco("hola", 3));
            print(eco("a", 2) == "a!!");
        """)


# ----------------------------------------------------------------------
# Casos fallidos en MARS
# ----------------------------------------------------------------------

@unittest.skipUnless(MARS_JAR, "requiere MARS_JAR y Java")
class TestMARSFallidos(unittest.TestCase):

    def test_indice_fuera_de_rango_atrapado(self):
        codigo = """
            let a: integer[] = [1, 2];
            let i: integer = 5;
            try { print(a[i]); } catch (e) { print("atrapado"); }
            print("sigue");
        """
        self.assertEqual(ejecutar_en_mars(compilar(codigo).asm), esperada(codigo))
        self.assertEqual(esperada(codigo), "atrapado\nsigue")

    def test_indice_negativo_atrapado(self):
        codigo = """
            let a: integer[] = [1, 2];
            let i: integer = -1;
            try { a[i] = 3; } catch (e) { print("negativo"); }
        """
        self.assertEqual(ejecutar_en_mars(compilar(codigo).asm), "negativo")

    def test_variables_al_dia_en_el_catch(self):
        # x solo estaba en un registro cuando falla el acceso: el catch la lee
        # de memoria, así que debe guardarse antes de verificar el índice.
        codigo = """
            let a: integer[] = [1];
            let x: integer = 0;
            try { x = 41; x = x + 1; print(a[3]); } catch (e) { print(x); }
        """
        self.assertEqual(ejecutar_en_mars(compilar(codigo).asm), esperada(codigo))
        self.assertEqual(esperada(codigo), "42")

    def test_error_en_funcion_atrapado_por_el_llamador(self):
        codigo = """
            function quinto(v: integer[]): integer { return v[5]; }
            try { print(quinto([1, 2])); } catch (e) { print("desde la funcion"); }
            print("fin");
        """
        self.assertEqual(ejecutar_en_mars(compilar(codigo).asm), esperada(codigo))

    def test_try_anidados(self):
        codigo = """
            let a: integer[] = [1];
            try {
              try { print(a[2]); } catch (e) { print("interno"); }
              print(a[3]);
            } catch (e) { print("externo"); }
            print("fin");
        """
        self.assertEqual(ejecutar_en_mars(compilar(codigo).asm), "interno\nexterno\nfin")

    def test_arreglo_null(self):
        codigo = """
            let a: integer[];
            try { print(a[0]); } catch (e) { print("null atrapado"); }
        """
        self.assertEqual(ejecutar_en_mars(compilar(codigo).asm), "null atrapado")

    def test_objeto_null(self):
        codigo = """
            class P { var x: integer; }
            let p: P;
            try { print(p.x); } catch (e) { print("objeto null"); }
            p = new P();
            p.x = 3;
            print(p.x);
        """
        self.assertEqual(ejecutar_en_mars(compilar(codigo).asm), "objeto null\n3")

    def test_no_atrapado_imprime_el_error_y_termina(self):
        codigo = """
            let a: integer[] = [1, 2];
            print("antes");
            print(a[2]);
            print("nunca");
        """
        resultado = analizar(codigo)
        self.assertIn("fuera de rango", resultado.ejecucion.error)
        self.assertEqual(ejecutar_en_mars(resultado.ensamblador.asm),
                         "antes\nindice fuera de rango")


if __name__ == "__main__":
    unittest.main()
