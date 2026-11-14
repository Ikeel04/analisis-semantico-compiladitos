"""
Árbol de activación: intérprete del TAC que registra cada llamada.

El árbol de activación depende de la ejecución (cuántas veces se llama
`factorial` depende del argumento), así que no se puede sacar del texto del
programa. Este módulo ejecuta el TAC con el mismo modelo de memoria del
backend —un marco por activación con sus parámetros, locales y temporales en
las direcciones `fp+N`— y anota cada activación como un nodo hijo de quien la
llamó. De paso produce la salida esperada del programa, que se compara con la
de MARS.

La ejecución tiene límites (pasos, profundidad y nodos dibujados) para que un
ciclo infinito o una recursión sin caso base no congelen la interfaz.
"""

from __future__ import annotations

import os
import struct
import sys
from dataclasses import dataclass, field

_SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_INTERMEDIO = os.path.join(_SRC, "intermediate")
if _INTERMEDIO not in sys.path:
    sys.path.insert(0, _INTERMEDIO)

import tac as T
from marcos import es_metodo
from tipos import FLOTANTE, InferenciaTipos, tipo_literal
from unidades import UNIDAD_PRINCIPAL, es_temporal, separar_unidades


class ErrorEjecucion(Exception):
    """Excepción de tiempo de ejecución de Compiscript (la atrapa un catch)."""


class LimiteEjecucion(Exception):
    """Se agotaron los pasos o la profundidad: se corta la ejecución."""


@dataclass
class NodoActivacion:
    numero: int
    funcion: str
    argumentos: list = field(default_factory=list)
    retorno: object = None
    devolvio: bool = False
    profundidad: int = 0
    tamano_marco: int = 0
    hijos: list = field(default_factory=list)

    def etiqueta(self) -> str:
        if self.funcion == UNIDAD_PRINCIPAL:
            return "main"
        mostrar = lambda v: f'"{v}"' if isinstance(v, str) else formatear(v)
        args = ", ".join(mostrar(a) for a in self.argumentos)
        texto = f"{self.funcion}({args})"
        if self.devolvio:
            texto += f" → {mostrar(self.retorno)}"
        return texto


def _a_float32(valor: float) -> float:
    return struct.unpack(">f", struct.pack(">f", float(valor)))[0]


def _a_int32(valor: int) -> int:
    valor &= 0xFFFFFFFF
    return valor - 0x100000000 if valor & 0x80000000 else valor


def formatear(valor) -> str:
    """Como lo imprime el programa en MARS."""
    if valor is True:
        return "true"
    if valor is False:
        return "false"
    if valor is None:
        return "null"
    if isinstance(valor, float):
        for digitos in range(1, 10):
            texto = f"{valor:.{digitos}g}"
            if _a_float32(float(texto)) == valor:
                break
        if "e" not in texto and "." not in texto and "inf" not in texto and "nan" not in texto:
            texto += ".0"
        return texto
    if isinstance(valor, list):
        return "[" + ", ".join(formatear(v) for v in valor) + "]"
    if isinstance(valor, dict):
        return f"<{valor.get('__clase__', 'objeto')}>"
    return str(valor)


@dataclass
class ResultadoEjecucion:
    raiz: NodoActivacion
    salida: list = field(default_factory=list)
    error: str | None = None
    pasos: int = 0
    activaciones: int = 0
    profundidad_maxima: int = 0
    nodos_omitidos: int = 0

    def nodos(self):
        pila = [self.raiz]
        while pila:
            nodo = pila.pop()
            yield nodo
            pila.extend(reversed(nodo.hijos))

    def como_texto(self) -> str:
        lineas = []

        def recorrer(nodo, prefijo, ultimo, raiz):
            conector = "" if raiz else ("└── " if ultimo else "├── ")
            lineas.append(prefijo + conector + nodo.etiqueta())
            hijo_prefijo = prefijo + ("" if raiz else ("    " if ultimo else "│   "))
            for i, hijo in enumerate(nodo.hijos):
                recorrer(hijo, hijo_prefijo, i == len(nodo.hijos) - 1, False)

        recorrer(self.raiz, "", True, True)
        if self.nodos_omitidos:
            lineas.append(f"… y {self.nodos_omitidos} activación(es) más")
        return "\n".join(lineas)

    def como_dot(self) -> str:
        """Árbol en DOT, para st.graphviz_chart."""
        lineas = ['digraph activacion {',
                  '  node [shape=box, style="rounded,filled", fillcolor="#EAF2FB", '
                  'color="#569CD6", fontname="Helvetica", fontsize=11];',
                  '  edge [color="#8A8A8A"];']
        for nodo in self.nodos():
            texto = nodo.etiqueta().replace("\\", "\\\\").replace('"', '\\"')
            lineas.append(f'  n{nodo.numero} [label="{texto}"];')
            for hijo in nodo.hijos:
                lineas.append(f"  n{nodo.numero} -> n{hijo.numero};")
        lineas.append("}")
        return "\n".join(lineas)

    def filas_para_ide(self) -> list[dict]:
        return [{"#": n.numero, "Activación": n.etiqueta(),
                 "Profundidad": n.profundidad,
                 "Marco": f"{n.tamano_marco} b" if n.tamano_marco else "-",
                 "Llamadas hechas": len(n.hijos)}
                for n in self.nodos()]


class _Marco:
    """Un marco de pila durante la ejecución."""

    def __init__(self, funcion, nodo, receptor=None):
        self.funcion = funcion
        self.nodo = nodo
        self.memoria: dict = {}        # fp+N y temporales
        self.receptor = receptor
        self.argumentos: list = []     # pila de `param` pendientes


class _Retorno(Exception):
    def __init__(self, valor):
        self.valor = valor


class InterpreteTAC:
    def __init__(self, programa, tabla, resumen, marcos=None,
                 max_pasos=200_000, max_nodos=300, max_profundidad=180):
        self.resumen = resumen
        self.tipos = InferenciaTipos(tabla, resumen)
        self.marcos_mips = marcos or {}
        self.max_pasos = max_pasos
        self.max_nodos = max_nodos
        self.max_profundidad = max_profundidad

        self.codigo: dict[str, list] = {}
        self.etiquetas: dict[str, dict] = {}
        for unidad in separar_unidades(programa):
            instrucciones = [c for _, c in unidad.instrucciones]
            self.codigo[unidad.nombre] = instrucciones
            self.etiquetas[unidad.nombre] = {
                c.arg1: i for i, c in enumerate(instrucciones) if c.op == T.ETIQUETA}

        self.atributos_por_offset = self._atributos_por_offset(tabla)
        self.globales: dict = {}
        self.pila: list[_Marco] = []
        self.salida: list[str] = []
        self.pasos = 0
        self.contador = 0
        self.omitidos = 0
        self.profundidad_maxima = 0

    @staticmethod
    def _atributos_por_offset(tabla) -> dict:
        """clase -> {offset: nombre del atributo}, con los heredados."""
        propios, padres = {}, {}
        for scope in tabla.global_scope.children:
            if scope.kind != "class":
                continue
            simbolo = tabla.global_scope.resolve_local(scope.name)
            if simbolo is not None and simbolo.extra.get("parent"):
                padres[scope.name] = simbolo.extra["parent"]
            propios[scope.name] = {
                s.offset: s.name for s in scope.symbols.values()
                if s.kind in ("variable", "constant") and s.offset is not None}
        resultado = {}
        for clase in propios:
            mapa, actual, vistos = {}, clase, set()
            while actual in propios and actual not in vistos:
                vistos.add(actual)
                for offset, nombre in propios[actual].items():
                    mapa.setdefault(offset, nombre)
                actual = padres.get(actual)
            resultado[clase] = mapa
        return resultado

    # ------------------------------------------------------------------
    # Ejecución
    # ------------------------------------------------------------------

    def ejecutar(self) -> ResultadoEjecucion:
        raiz = NodoActivacion(0, UNIDAD_PRINCIPAL)
        resultado = ResultadoEjecucion(raiz)
        marco = _Marco(UNIDAD_PRINCIPAL, raiz)
        self.pila.append(marco)
        try:
            self._ejecutar_unidad(marco)
        except ErrorEjecucion as e:
            resultado.error = f"Excepción no atrapada: {e}"
        except LimiteEjecucion as e:
            resultado.error = str(e)
        except RecursionError:
            resultado.error = "Se superó la profundidad de recursión del intérprete."
        resultado.salida = self.salida
        resultado.pasos = self.pasos
        resultado.activaciones = self.contador
        resultado.profundidad_maxima = self.profundidad_maxima
        resultado.nodos_omitidos = self.omitidos
        return resultado

    def _ejecutar_unidad(self, marco) -> object:
        instrucciones = self.codigo.get(marco.funcion, [])
        etiquetas = self.etiquetas.get(marco.funcion, {})
        pc = 0
        while pc < len(instrucciones):
            self.pasos += 1
            if self.pasos > self.max_pasos:
                raise LimiteEjecucion(
                    f"Se detuvo la ejecución tras {self.max_pasos} instrucciones "
                    "(¿ciclo infinito?).")
            c = instrucciones[pc]
            try:
                salto = self._ejecutar_instruccion(c, marco)
            except _Retorno as r:
                return r.valor
            except ErrorEjecucion:
                catch = self._buscar_catch(instrucciones, pc)
                if catch is None:
                    raise
                pc = etiquetas[catch]
                continue
            pc = etiquetas[salto] if salto is not None else pc + 1
        return None

    @staticmethod
    def _buscar_catch(instrucciones, pc) -> str | None:
        """Etiqueta del catch que protege la instrucción `pc`.

        Con marcadores `# try <catch>` / `# fin try <catch>` en el TAC se usa
        el try más interno que encierra a `pc`. Sin marcadores se usa el
        patrón de traducción del try: `goto L_fin` seguido de `L_catch:`.
        """
        abiertos = []
        con_marcadores = False
        for i, c in enumerate(instrucciones):
            if c.op == T.COMENTARIO and isinstance(c.arg1, str):
                partes = c.arg1.split()
                if partes[:1] == ["try"] and len(partes) == 2:
                    con_marcadores = True
                    if i <= pc:
                        abiertos.append(partes[1])
                elif partes[:2] == ["fin", "try"] and len(partes) == 3 and i <= pc:
                    if partes[2] in abiertos:
                        abiertos.remove(partes[2])
        if con_marcadores:
            return abiertos[-1] if abiertos else None
        for i in range(pc, len(instrucciones) - 1):
            c, siguiente = instrucciones[i], instrucciones[i + 1]
            if (c.op == T.SALTAR and siguiente.op == T.ETIQUETA
                    and "catch" in siguiente.arg1):
                return siguiente.arg1
            if c.op == T.ETIQUETA and "catch" in c.arg1:
                return None    # ya estamos dentro de un catch
        return None

    # ------------------------------------------------------------------
    # Valores
    # ------------------------------------------------------------------

    def _leer(self, operando, marco):
        if not isinstance(operando, str):      # newarray 3 guarda el entero tal cual
            return operando
        tipo = tipo_literal(operando)
        if tipo is not None:
            return self._literal(operando, tipo)
        if operando == "this":
            return marco.receptor
        if operando.startswith("global+"):
            return self.globales.get(operando, 0)
        if operando.startswith("obj+"):
            objeto = marco.receptor
            return objeto.get(self._campo(objeto, operando)) if isinstance(objeto, dict) else None
        if operando.startswith("fp+") or es_temporal(operando):
            return marco.memoria.get(operando, 0)
        return self._capturada(operando, marco)

    def _escribir(self, destino, valor, marco) -> None:
        if destino.startswith("global+"):
            self.globales[destino] = valor
        elif destino.startswith("obj+") and isinstance(marco.receptor, dict):
            marco.receptor[self._campo(marco.receptor, destino)] = valor
        elif destino.startswith("fp+") or es_temporal(destino):
            marco.memoria[destino] = valor
        else:
            self._escribir_capturada(destino, valor, marco)

    def _campo(self, objeto, operando) -> str:
        offset = int(operando.split("+")[1])
        return self.atributos_por_offset.get(objeto.get("__clase__"), {}).get(offset, operando)

    def _direccion_capturada(self, nombre, marco):
        """Una variable de la función que encierra a esta (closure): se busca
        en la activación más reciente de esa función."""
        partes = marco.funcion.split(".")
        for corte in range(len(partes) - 1, 0, -1):
            externa = ".".join(partes[:corte])
            registro = self.resumen.registros.get(externa)
            if registro is None:
                continue
            for simbolo in list(registro.parametros) + list(registro.locales):
                if simbolo.name == nombre:
                    for otro in reversed(self.pila):
                        if otro.funcion == externa:
                            return otro, simbolo.direccion
        return None, None

    def _capturada(self, nombre, marco):
        otro, direccion = self._direccion_capturada(nombre, marco)
        return otro.memoria.get(direccion, 0) if otro is not None else None

    def _escribir_capturada(self, nombre, valor, marco) -> None:
        otro, direccion = self._direccion_capturada(nombre, marco)
        if otro is not None:
            otro.memoria[direccion] = valor

    @staticmethod
    def _literal(texto, tipo):
        if tipo == "integer":
            return int(texto)
        if tipo == FLOTANTE:
            return _a_float32(float(texto))
        if tipo == "boolean":
            return texto == "true"
        if tipo == "string":
            cuerpo = texto[1:-1]
            for escape, caracter in (("\\n", "\n"), ("\\t", "\t"), ('\\"', '"'), ("\\\\", "\\")):
                cuerpo = cuerpo.replace(escape, caracter)
            return cuerpo
        return None

    def _valor_por_defecto(self, tipo):
        return {"integer": 0, "float": 0.0, "boolean": False}.get(tipo)

    # ------------------------------------------------------------------
    # Instrucciones
    # ------------------------------------------------------------------

    def _ejecutar_instruccion(self, c, marco):
        op = c.op
        leer = lambda o: self._leer(o, marco)
        if op == T.ASIGNAR:
            valor = leer(c.arg1)
            if isinstance(valor, int) and not isinstance(valor, bool) and \
                    self.tipos.tipo_de(c.resultado, marco.funcion, {}) == FLOTANTE:
                valor = _a_float32(valor)
            self._escribir(c.resultado, valor, marco)
        elif op in T.BINARIAS:
            self._escribir(c.resultado, self._binaria(op, leer(c.arg1), leer(c.arg2)), marco)
        elif op == T.NEGATIVO:
            valor = leer(c.arg1)
            self._escribir(c.resultado, -valor if isinstance(valor, float) else _a_int32(-valor), marco)
        elif op == T.NEGACION:
            self._escribir(c.resultado, not leer(c.arg1), marco)
        elif op == T.SALTAR:
            return c.resultado
        elif op == T.SALTAR_SI:
            return c.resultado if leer(c.arg1) else None
        elif op == T.SALTAR_SI_FALSO:
            return None if leer(c.arg1) else c.resultado
        elif op == T.PRINT:
            self.salida.append(formatear(leer(c.arg1)))
        elif op == T.PARAMETRO:
            marco.argumentos.append(leer(c.arg1))
        elif op == T.LLAMAR:
            cantidad = int(c.arg2)
            argumentos = marco.argumentos[len(marco.argumentos) - cantidad:] if cantidad else []
            del marco.argumentos[len(marco.argumentos) - cantidad:]
            valor = self._llamar(c.arg1, argumentos, marco)
            if c.resultado is not None:
                self._escribir(c.resultado, valor, marco)
        elif op == T.RETORNAR:
            raise _Retorno(None if c.arg1 is None else leer(c.arg1))
        elif op == T.NUEVO_ARREGLO:
            self._escribir(c.resultado, [0] * int(leer(c.arg1)), marco)
        elif op == T.LEER_INDICE:
            arreglo, indice = leer(c.arg1), leer(c.arg2)
            self._verificar_indice(arreglo, indice)
            self._escribir(c.resultado, arreglo[indice], marco)
        elif op == T.ESCRIBIR_INDICE:
            arreglo, indice = leer(c.resultado), leer(c.arg1)
            self._verificar_indice(arreglo, indice)
            arreglo[indice] = leer(c.arg2)
        elif op == T.LONGITUD:
            arreglo = leer(c.arg1)
            if not isinstance(arreglo, list):
                raise ErrorEjecucion("length de un valor que no es arreglo")
            self._escribir(c.resultado, len(arreglo), marco)
        elif op == T.NUEVO:
            objeto = {"__clase__": c.arg1}
            clase = c.arg1
            while clase is not None:
                for campo, tipo in self.tipos.atributos.get(clase, {}).items():
                    objeto.setdefault(campo, self._valor_por_defecto(tipo))
                clase = self.tipos.padres.get(clase)
            self._escribir(c.resultado, objeto, marco)
        elif op == T.LEER_CAMPO:
            objeto = leer(c.arg1)
            if not isinstance(objeto, dict):
                raise ErrorEjecucion(f"acceso a '{c.arg2}' de null")
            self._escribir(c.resultado, objeto.get(c.arg2), marco)
        elif op == T.ESCRIBIR_CAMPO:
            objeto = leer(c.resultado)
            if not isinstance(objeto, dict):
                raise ErrorEjecucion(f"asignación a '{c.arg1}' de null")
            objeto[c.arg1] = leer(c.arg2)
        return None

    @staticmethod
    def _verificar_indice(arreglo, indice) -> None:
        if not isinstance(arreglo, list):
            raise ErrorEjecucion("acceso por índice a un valor que no es arreglo")
        if not isinstance(indice, int) or not 0 <= indice < len(arreglo):
            raise ErrorEjecucion(f"índice {indice} fuera de rango (tamaño {len(arreglo)})")

    @staticmethod
    def _binaria(op, a, b):
        if op == T.SUMA and (isinstance(a, str) or isinstance(b, str)):
            return formatear(a) + formatear(b)
        if op == T.Y_LOGICO:
            return bool(a) and bool(b)
        if op == T.O_LOGICO:
            return bool(a) or bool(b)
        if op in (T.IGUAL, T.DISTINTO):
            if isinstance(a, (list, dict)) or isinstance(b, (list, dict)):
                igual = a is b
            else:
                igual = a == b
            return igual if op == T.IGUAL else not igual
        if op == T.MENOR:
            return a < b
        if op == T.MENOR_IGUAL:
            return a <= b
        if op == T.MAYOR:
            return a > b
        if op == T.MAYOR_IGUAL:
            return a >= b
        flotante = isinstance(a, float) or isinstance(b, float)
        if op in (T.DIVISION, T.MODULO) and b == 0:
            raise ErrorEjecucion("división por cero")
        if flotante:
            resultado = {T.SUMA: lambda: a + b, T.RESTA: lambda: a - b,
                         T.MULTIPLICACION: lambda: a * b,
                         T.DIVISION: lambda: a / b, T.MODULO: lambda: a % b}[op]()
            return _a_float32(resultado)
        if op == T.DIVISION:
            cociente = abs(a) // abs(b)
            return _a_int32(cociente if (a < 0) == (b < 0) else -cociente)
        if op == T.MODULO:
            resto = abs(a) % abs(b)
            return _a_int32(resto if a >= 0 else -resto)
        return _a_int32({T.SUMA: a + b, T.RESTA: a - b, T.MULTIPLICACION: a * b}[op])

    def _llamar(self, funcion, argumentos, llamador) -> object:
        profundidad = len(self.pila)
        if profundidad > self.max_profundidad:
            raise LimiteEjecucion(
                f"Se superaron {self.max_profundidad} activaciones anidadas "
                "(¿recursión sin caso base?).")
        self.profundidad_maxima = max(self.profundidad_maxima, profundidad)

        metodo = es_metodo(funcion, self.tipos.clases)
        receptor = argumentos[0] if metodo and argumentos else None
        valores = argumentos[1:] if metodo else argumentos

        self.contador += 1
        marco_mips = self.marcos_mips.get(funcion)
        nodo = NodoActivacion(self.contador, funcion, list(valores),
                              profundidad=profundidad,
                              tamano_marco=marco_mips.tamano if marco_mips else 0)
        if self.contador <= self.max_nodos:
            llamador.nodo.hijos.append(nodo)
        else:
            self.omitidos += 1

        marco = _Marco(funcion, nodo, receptor)
        registro = self.resumen.registros.get(funcion)
        if registro is not None:
            for simbolo, valor in zip(registro.parametros, valores):
                if simbolo.type == FLOTANTE and isinstance(valor, int) and not isinstance(valor, bool):
                    valor = _a_float32(valor)
                marco.memoria[simbolo.direccion] = valor

        self.pila.append(marco)
        try:
            valor = self._ejecutar_unidad(marco)
        finally:
            self.pila.pop()
        nodo.retorno = valor
        nodo.devolvio = valor is not None or self.tipos.retornos.get(funcion) not in (None, "void")
        return valor


def construir_arbol(programa, tabla, resumen, marcos=None) -> ResultadoEjecucion:
    """Ejecuta el TAC y devuelve el árbol de activación y la salida."""
    return InterpreteTAC(programa, tabla, resumen, marcos).ejecutar()
