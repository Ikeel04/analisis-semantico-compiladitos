"""
Tests de la traducción TAC -> MIPS: registros de activación, convención de
llamada, variables, expresiones aritméticas y lógicas, float y print.

Los tests de `TestEjecucionMARS` ensamblan y ejecutan el código en MARS. Solo
corren si la variable de entorno MARS_JAR apunta a Mars4_5.jar (y hay Java):

    set MARS_JAR=C:\\ruta\\Mars4_5.jar      (Windows)
    export MARS_JAR=/ruta/Mars4_5.jar       (Linux / macOS)

Corre con: python -m unittest discover -s tests -v
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

_BASE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(_BASE, "..", "src", "compiler"))
sys.path.insert(0, os.path.join(_BASE, "..", "src", "backend"))

from pipeline import analizar_codigo
from backend import generar_ensamblador

MARS_JAR = os.environ.get("MARS_JAR")


def compilar(codigo):
    resultado = analizar_codigo("test.cps", codigo)
    assert resultado.genero_tac, [str(e) for e in resultado.errores]
    return generar_ensamblador(resultado.tac, resultado.tabla, resultado.memoria)


def ejecutar_en_mars(asm: str) -> str:
    carpeta = tempfile.mkdtemp()
    try:
        ruta = os.path.join(carpeta, "programa.asm")
        with open(ruta, "w", encoding="utf-8") as fh:
            fh.write(asm)
        salida = subprocess.run(["java", "-jar", MARS_JAR, "nc", ruta],
                                capture_output=True, text=True, timeout=60)
        return salida.stdout.strip().replace("\r\n", "\n")
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)


def lineas(asm):
    return [l.strip() for l in asm.splitlines()]


class TestEstructura(unittest.TestCase):

    def test_secciones_y_main(self):
        asm = compilar("let x: integer = 1;").asm
        self.assertIn(".data", asm)
        self.assertIn("__globales: .space", asm)
        self.assertIn(".text", asm)
        self.assertIn("main:", asm)
        self.assertIn("la      $s7, __globales", asm)

    def test_termina_con_syscall_10(self):
        asm = lineas(compilar("let x: integer = 1;").asm)
        i = asm.index("main:")
        cuerpo = asm[i:]
        self.assertIn("li      $v0, 10                 # fin del programa", cuerpo)

    def test_cadenas_en_data_sin_repetir(self):
        asm = compilar('print("hola"); print("hola"); print("adios");').asm
        self.assertEqual(asm.count('.asciiz "hola"'), 1)
        self.assertIn('.asciiz "adios"', asm)

    def test_sin_pendientes_en_expresiones(self):
        resultado = compilar("let a: integer = 2; let b: boolean = a < 3 && !(a == 1);")
        self.assertEqual(resultado.pendientes, [])

    def test_operaciones_sin_manejador_quedan_pendientes(self):
        resultado = compilar("let a: integer[] = [1, 2];")
        self.assertTrue(resultado.pendientes)
        self.assertIn("[pendiente]", resultado.asm)


class TestExtensiones(unittest.TestCase):

    def test_extension_registra_manejador_y_rutina(self):
        import extensiones
        import tac as T

        def emitir_rutina(programa):
            programa.etiqueta("__prueba")
            programa.emitir("jr", "$ra")

        def registrar(traductor):
            def etiqueta(c):
                traductor.mips.etiqueta(c.arg1)
                traductor.mips.emitir("jal", traductor.mips.usar_rutina("__prueba", emitir_rutina))
            traductor.manejadores[T.ETIQUETA] = etiqueta

        extensiones.EXTENSIONES.append(registrar)
        try:
            resultado = compilar("let a: integer = 1; if (a > 0) { print(a); }")
        finally:
            extensiones.EXTENSIONES.remove(registrar)
        self.assertIn("__prueba:", resultado.asm)
        self.assertEqual(resultado.asm.count("__prueba:"), 1)
        self.assertNotIn("[pendiente] L", resultado.asm_sin_optimizar)


class TestCompuerta(unittest.TestCase):

    def test_con_errores_no_hay_ensamblador(self):
        resultado = analizar_codigo("test.cps", "let x: integer = true; print(y);")
        self.assertFalse(resultado.genero_asm)
        self.assertIsNone(resultado.ejecucion)

    def test_sin_errores_hay_ensamblador_y_arbol(self):
        resultado = analizar_codigo("test.cps", "let x: integer = 1; print(x);")
        self.assertTrue(resultado.genero_asm)
        self.assertIn("main:", resultado.ensamblador.asm)
        self.assertEqual(resultado.ejecucion.salida, ["1"])


class TestRegistrosDeActivacion(unittest.TestCase):

    CODIGO = """
    function suma(a: integer, b: integer): integer {
      var c: integer = a + b;
      return c;
    }
    let r: integer = suma(2, 3);
    """

    def test_marco_con_parametros_locales_y_temporales(self):
        marco = compilar(self.CODIGO).marcos["suma"]
        celdas = {c.nombre: c.offset for c in marco.celdas()}
        self.assertEqual(celdas["enlace de control"], 0)
        self.assertEqual(celdas["dirección de retorno"], 8)
        self.assertEqual(celdas["a"], 16)
        self.assertEqual(celdas["b"], 20)
        self.assertEqual(celdas["c"], 24)
        self.assertEqual(marco.tamano % 8, 0)
        self.assertEqual(marco.argumentos, 2)

    def test_argumentos_se_leen_sobre_el_marco(self):
        marco = compilar(self.CODIGO).marcos["suma"]
        # El primero apilado es el más profundo.
        self.assertEqual(marco.offset_argumento(0), marco.tamano + 4)
        self.assertEqual(marco.offset_argumento(1), marco.tamano)

    def test_prologo_y_epilogo(self):
        asm = compilar(self.CODIGO).asm
        marco = compilar(self.CODIGO).marcos["suma"]
        self.assertIn("fn_suma:", asm)
        self.assertIn(f"addiu   $sp, $sp, -{marco.tamano}", asm)
        self.assertIn("sw      $fp, 0($sp)", asm)
        self.assertIn("sw      $ra, 8($sp)", asm)
        self.assertIn("fn_suma_fin:", asm)
        self.assertIn("jr      $ra", asm)

    def test_llamada_apila_salta_y_desapila(self):
        texto = lineas(compilar(self.CODIGO).asm_sin_optimizar)
        jal = texto.index("jal     fn_suma")
        self.assertTrue(texto[jal + 1].startswith("addiu   $sp, $sp, 8"))
        self.assertTrue(any(l.startswith("move") and l.endswith("$v0") for l in texto[jal:jal + 4]))
        self.assertEqual(sum(1 for l in texto if l.startswith("sw") and "0($sp)" in l
                             and "param" in l), 2)

    def test_return_salta_al_epilogo(self):
        # Sin optimizar está el salto; la mirilla lo quita porque el epílogo
        # es la línea siguiente.
        resultado = compilar(self.CODIGO)
        self.assertIn("j       fn_suma_fin", resultado.asm_sin_optimizar)
        self.assertNotIn("j       fn_suma_fin", resultado.asm)

    def test_boolean_en_marco_usa_byte(self):
        asm = compilar("""
        function f(b: boolean): boolean { return !b; }
        let x: boolean = f(true);
        """).asm
        self.assertIn("sb      $a2, 16($fp)", asm)
        self.assertIn("lbu", asm)

    def test_metodo_reserva_celda_para_this(self):
        resultado = compilar("""
        class C {
          var n: integer;
          function constructor(n: integer) { this.n = n; }
        }
        let c: C = new C(1);
        """)
        marco = resultado.marcos["C.constructor"]
        self.assertTrue(marco.es_metodo)
        self.assertEqual(marco.argumentos, 2)
        self.assertIn("this", [c.nombre for c in marco.celdas()])

    def test_funcion_anidada_tiene_su_propio_marco(self):
        marcos = compilar("""
        function externa(): integer {
          function interna(x: integer): integer { return x; }
          return interna(1);
        }
        let r: integer = externa();
        """).marcos
        self.assertIn("externa", marcos)
        self.assertIn("externa.interna", marcos)

    def test_temporales_vivos_se_guardan_antes_del_call(self):
        asm = compilar("""
        function f(n: integer): integer { return n; }
        let r: integer = f(1) + f(2);
        """).asm
        self.assertIn("antes de call", asm)


class TestExpresiones(unittest.TestCase):

    def instrucciones(self, codigo):
        return [l.split()[0] for l in lineas(compilar(codigo).asm)
                if l and not l.endswith(":") and not l.startswith(("#", "."))]

    def test_aritmeticas(self):
        ops = self.instrucciones("""
        let a: integer = 7; let b: integer = 2;
        let c: integer = a + b; let d: integer = a - b; let e: integer = a * b;
        let f: integer = a / b; let g: integer = a % b;
        """)
        for op in ("addu", "subu", "mul", "div", "mflo", "mfhi"):
            self.assertIn(op, ops)

    def test_inmediatos(self):
        asm = compilar("let a: integer = 1; let b: integer = a + 5; let c: integer = a - 3;").asm
        self.assertIn("addiu", asm)
        self.assertIn(", -3", asm)

    def test_relacionales_y_logicas(self):
        ops = self.instrucciones("""
        let a: integer = 1; let b: integer = 2;
        let p: boolean = a < b; let q: boolean = a <= b; let r: boolean = a > b;
        let s: boolean = a >= b; let t: boolean = a == b; let u: boolean = a != b;
        let v: boolean = p && q; let w: boolean = p || q; let x: boolean = !p;
        """)
        for op in ("slt", "sle", "sgt", "sge", "seq", "sne", "and", "or", "xori"):
            self.assertIn(op, ops)

    def test_negativo(self):
        self.assertIn("subu", self.instrucciones("let a: integer = 1; let b: integer = -a;"))

    def test_float(self):
        ops = self.instrucciones(
            "let n: integer = 1; let x: float = 1.5; let y: float = x * 2.0 + n;")
        for op in ("mtc1", "mul.s", "add.s", "cvt.s.w", "mfc1"):
            self.assertIn(op, ops)

    def test_entero_asignado_a_float_se_convierte(self):
        asm = compilar("let x: float = 3;").asm
        self.assertIn("0x40400000", asm)      # 3.0 en IEEE-754

    def test_print_por_tipo(self):
        asm = compilar("""
        print(1); print("s"); print(true); print(1.5);
        """).asm
        for codigo in ("li      $v0, 1", "li      $v0, 4", "li      $v0, 2", "movz"):
            self.assertIn(codigo, asm)

    def test_traza_por_cuadruplo(self):
        resultado = compilar("let a: integer = 1; let b: integer = a + 2;")
        self.assertTrue(resultado.traza)
        fila = resultado.traza[-1]
        self.assertIn("TAC", fila)
        self.assertIn("MIPS", fila)
        self.assertIn("Descriptor de registros", fila)

    def test_presion_de_registros_provoca_desalojos(self):
        nombres = [f"v{i}" for i in range(20)]
        codigo = "".join(f"let {n}: integer = {i};" for i, n in enumerate(nombres))
        suma = " + ".join(f"({n} * {n})" for n in nombres)
        codigo += f"let total: integer = {suma}; print(total);"
        resultado = compilar(codigo)
        self.assertGreater(resultado.registros["main"]["desalojos"], 0)


@unittest.skipUnless(MARS_JAR and shutil.which("java"), "requiere MARS_JAR y Java")
class TestEjecucionMARS(unittest.TestCase):

    def ejecutar(self, codigo):
        return ejecutar_en_mars(compilar(codigo).asm)

    def test_variables_y_constantes(self):
        self.assertEqual(self.ejecutar("""
        const MAX: integer = 100;
        let s: string = "hola";
        var b: boolean = true;
        let x: integer;
        x = MAX + 1;
        print(MAX); print(s); print(b); print(x);
        """), "100\nhola\ntrue\n101")

    def test_aritmeticas(self):
        self.assertEqual(self.ejecutar("""
        let a: integer = 6; let b: integer = 4; let c: integer = 3;
        print(a + b * c); print((a + b) * (c - 1)); print(-a + b % c);
        print(a / b - c * 2); print(-17 / 5); print(17 % 5);
        """), "18\n20\n-5\n-5\n-3\n2")

    def test_logicas(self):
        self.assertEqual(self.ejecutar("""
        let x: integer = 5; let y: integer = 10;
        print(x < y && y > 3); print(x == 5 || y == 0);
        print(!(x >= y)); print((x != y && false) || x > y);
        """), "true\ntrue\ntrue\nfalse")

    def test_float(self):
        self.assertEqual(self.ejecutar("""
        let x: float = 2.5;
        let y: float = x * 4 + 1.5;
        print(y); print(y / 2.0 - 0.25); print(y > x); print(-x);
        """), "11.5\n5.5\ntrue\n-2.5")

    def test_funciones_y_marcos(self):
        self.assertEqual(self.ejecutar("""
        function mezcla(p: integer, q: boolean, r: integer, s: float): integer {
          var loc: integer = p * r;
          print(!q);
          print(s);
          return loc + p - r;
        }
        function doble(v: integer): integer { return v * 2; }
        function cuadruple(v: integer): integer { return doble(doble(v)); }
        print(mezcla(6, true, 7, 1.25));
        print(cuadruple(5) + doble(3) * cuadruple(doble(1)));
        """), "false\n1.25\n41\n68")

    def test_presion_de_registros(self):
        nombres = [f"v{i}" for i in range(20)]
        codigo = "".join(f"let {n}: integer = {i};" for i, n in enumerate(nombres))
        suma = " + ".join(f"({n} * {n})" for n in nombres)
        codigo += f"print({suma});"
        self.assertEqual(self.ejecutar(codigo), str(sum(i * i for i in range(20))))


if __name__ == "__main__":
    unittest.main()
