"""
Optimización por mirilla sobre el ensamblador generado.

Cada regla mira una ventana pequeña de instrucciones consecutivas y la
reemplaza por una equivalente más corta o más barata. Las reglas se aplican en
rondas hasta que ninguna cambia nada (una transformación suele habilitar
otra: quitar un salto deja una etiqueta sin uso, etc.). La tabla de reglas está
en docs/DISENO_MIPS.md §7.
"""

from __future__ import annotations

import re

from programa_mips import SALTO_INVERSO, Instr

_INTERNA = re.compile(r"^(L\d|__L)")
_MEMORIA = re.compile(r"^(-?\d+)\((\$\w+)\)$")
_LIMITE_RONDAS = 50


def _es_etiqueta_interna(nombre: str) -> bool:
    """Solo las etiquetas del TAC (L1, L2_fin…) se pueden borrar; las de
    funciones y main son puntos de entrada."""
    return bool(_INTERNA.match(nombre))


def _potencia_de_dos(texto: str) -> int | None:
    try:
        valor = int(texto)
    except ValueError:
        return None
    if valor > 1 and valor & (valor - 1) == 0:
        return valor.bit_length() - 1
    return None


def _base_memoria(operando: str) -> str | None:
    m = _MEMORIA.match(operando)
    return m.group(2) if m else None


class OptimizadorMirilla:
    def __init__(self):
        self.reglas = [
            ("Movimiento redundante", self.movimiento_redundante),
            ("Carga tras almacenamiento", self.carga_tras_almacenamiento),
            ("Almacenamiento redundante", self.almacenamiento_redundante),
            ("Identidades algebraicas", self.identidades_algebraicas),
            ("Reducción de fuerza", self.reduccion_de_fuerza),
            ("Fusión de ajustes de pila", self.ajustes_de_pila),
            ("Código inalcanzable", self.codigo_inalcanzable),
            ("Salto a la siguiente instrucción", self.salto_a_siguiente),
            ("Cadena de saltos", self.cadena_de_saltos),
            ("Salto sobre salto", self.salto_sobre_salto),
            ("Etiquetas sin uso", self.etiquetas_sin_uso),
        ]

    def optimizar(self, instrucciones: list[Instr]) -> tuple[list[Instr], dict]:
        lista = list(instrucciones)
        aplicadas = {nombre: 0 for nombre, _ in self.reglas}
        for _ in range(_LIMITE_RONDAS):
            cambio = False
            for nombre, regla in self.reglas:
                veces = regla(lista)
                if veces:
                    aplicadas[nombre] += veces
                    cambio = True
            if not cambio:
                break
        return lista, aplicadas

    # ------------------------------------------------------------------
    # Utilidades de la ventana
    # ------------------------------------------------------------------

    @staticmethod
    def _siguiente(lista, i) -> int | None:
        """Índice de la siguiente instrucción real (no comentario) después de i."""
        j = i + 1
        while j < len(lista) and lista[j].es_comentario:
            j += 1
        return j if j < len(lista) else None

    @staticmethod
    def _pares(lista):
        """(i, j) de instrucciones reales consecutivas, sin etiqueta entre ellas."""
        i = 0
        while i < len(lista):
            if not lista[i].es_comentario and not lista[i].es_etiqueta:
                j = OptimizadorMirilla._siguiente(lista, i)
                if j is not None and not lista[j].es_etiqueta:
                    yield i, j
            i += 1

    # ------------------------------------------------------------------
    # Reglas
    # ------------------------------------------------------------------

    def movimiento_redundante(self, lista) -> int:
        """move $x, $x"""
        antes = len(lista)
        lista[:] = [i for i in lista
                    if not (i.op == "move" and i.args[0] == i.args[1])]
        return antes - len(lista)

    def carga_tras_almacenamiento(self, lista) -> int:
        """sw R, M / lw S, M  ->  sw R, M / move S, R (nada si S == R)."""
        for i, j in self._pares(lista):
            a, b = lista[i], lista[j]
            if a.op == "sw" and b.op == "lw" and a.args[1] == b.args[1]:
                if a.args[0] == b.args[0]:
                    del lista[j]
                else:
                    lista[j] = Instr("move", (b.args[0], a.args[0]),
                                     "carga reemplazada por copia")
                return 1
        return 0

    def almacenamiento_redundante(self, lista) -> int:
        """lw R, M / sw R, M  ->  lw R, M (la memoria ya tiene ese valor)."""
        for i, j in self._pares(lista):
            a, b = lista[i], lista[j]
            if ((a.op, b.op) in (("lw", "sw"), ("lbu", "sb"))
                    and a.args == b.args and _base_memoria(a.args[1]) != a.args[0]):
                del lista[j]
                return 1
        return 0

    def identidades_algebraicas(self, lista) -> int:
        """x + 0, x - 0, x | 0, x * 1, x << 0 -> move; x * 0 -> li 0."""
        veces = 0
        for k, ins in enumerate(lista):
            nuevo = None
            a = ins.args
            if ins.op in ("addiu", "addi", "sll", "srl", "sra", "ori") and len(a) == 3 and a[2] == "0":
                nuevo = Instr("move", (a[0], a[1]))
            elif ins.op in ("addu", "add", "or", "subu", "sub") and len(a) == 3 and a[2] == "$zero":
                nuevo = Instr("move", (a[0], a[1]))
            elif ins.op in ("addu", "add", "or") and len(a) == 3 and a[1] == "$zero":
                nuevo = Instr("move", (a[0], a[2]))
            elif ins.op == "mul" and len(a) == 3 and a[2] == "1":
                nuevo = Instr("move", (a[0], a[1]))
            elif ins.op == "mul" and len(a) == 3 and a[2] == "0":
                nuevo = Instr("li", (a[0], "0"))
            if nuevo is not None:
                nuevo.comentario = f"era {ins.op} {', '.join(a)}"
                lista[k] = nuevo
                veces += 1
        return veces

    def reduccion_de_fuerza(self, lista) -> int:
        """mul d, s, 2^k  ->  sll d, s, k"""
        veces = 0
        for k, ins in enumerate(lista):
            if ins.op == "mul" and len(ins.args) == 3:
                exponente = _potencia_de_dos(ins.args[2])
                if exponente is not None:
                    lista[k] = Instr("sll", (ins.args[0], ins.args[1], str(exponente)),
                                     f"era mul por {ins.args[2]}")
                    veces += 1
        return veces

    def ajustes_de_pila(self, lista) -> int:
        """addiu $sp,$sp,a / sw X, o($sp)… / addiu $sp,$sp,b
        -> addiu $sp,$sp,a+b / sw X, o-b($sp)…  (cada `param` apila por separado;
        así una llamada de n argumentos mueve $sp una sola vez)."""
        def es_ajuste(ins):
            return ins.op == "addiu" and ins.args[:2] == ("$sp", "$sp")

        for i, ins in enumerate(lista):
            if not es_ajuste(ins):
                continue
            intermedios = []
            j = self._siguiente(lista, i)
            while (j is not None and lista[j].op == "sw"
                   and _base_memoria(lista[j].args[1]) == "$sp"
                   and lista[j].args[0] != "$sp"):
                intermedios.append(j)
                j = self._siguiente(lista, j)
            if j is None or not es_ajuste(lista[j]):
                continue
            b = int(lista[j].args[2])
            total = int(ins.args[2]) + b
            for k in intermedios:
                desplazamiento = int(_MEMORIA.match(lista[k].args[1]).group(1)) - b
                lista[k] = Instr("sw", (lista[k].args[0], f"{desplazamiento}($sp)"),
                                 lista[k].comentario)
            del lista[j]
            if total == 0 and not intermedios:
                del lista[i]
            else:
                lista[i] = Instr("addiu", ("$sp", "$sp", str(total)), ins.comentario)
            return 1
        return 0

    def codigo_inalcanzable(self, lista) -> int:
        """Lo que sigue a un salto incondicional, hasta la próxima etiqueta."""
        veces = 0
        k = 0
        while k < len(lista):
            if lista[k].es_salto_incondicional:
                j = k + 1
                while j < len(lista) and not lista[j].es_etiqueta:
                    if lista[j].es_comentario:
                        j += 1
                    else:
                        del lista[j]
                        veces += 1
            k += 1
        return veces

    def salto_a_siguiente(self, lista) -> int:
        """j L / L:  ->  L:  (también un salto condicional a la siguiente línea)."""
        for k, ins in enumerate(lista):
            destino = ins.destino
            if destino is None:
                continue
            j = k + 1
            while j < len(lista) and (lista[j].es_comentario or lista[j].es_etiqueta):
                if lista[j].es_etiqueta and lista[j].args[0] == destino:
                    del lista[k]
                    return 1
                j += 1
        return 0

    def cadena_de_saltos(self, lista) -> int:
        """j L1 … L1: j L2  ->  j L2"""
        posiciones = {ins.args[0]: k for k, ins in enumerate(lista) if ins.es_etiqueta}
        veces = 0
        for k, ins in enumerate(lista):
            destino = ins.destino
            if destino is None or destino not in posiciones:
                continue
            j = posiciones[destino] + 1
            while j < len(lista) and (lista[j].es_comentario or lista[j].es_etiqueta):
                j += 1
            if j < len(lista) and lista[j].op in ("j", "b"):
                final = lista[j].args[0]
                if final != destino:
                    lista[k] = ins.con_destino(final)
                    veces += 1
        return veces

    def salto_sobre_salto(self, lista) -> int:
        """beqz R, L1 / j L2 / L1:  ->  bnez R, L2 / L1:"""
        for k, ins in enumerate(lista):
            if not ins.es_salto_condicional or ins.op not in SALTO_INVERSO:
                continue
            j = self._siguiente(lista, k)
            if j is None or lista[j].op not in ("j", "b"):
                continue
            m = self._siguiente(lista, j)
            if m is not None and lista[m].es_etiqueta and lista[m].args[0] == ins.destino:
                invertido = Instr(SALTO_INVERSO[ins.op], ins.args, ins.comentario)
                lista[k] = invertido.con_destino(lista[j].args[0])
                del lista[j]
                return 1
        return 0

    def etiquetas_sin_uso(self, lista) -> int:
        usadas = {ins.destino for ins in lista if ins.destino is not None}
        usadas |= {a for ins in lista if ins.op in ("la", "jal") for a in ins.args}
        antes = len(lista)
        lista[:] = [ins for ins in lista
                    if not (ins.es_etiqueta and _es_etiqueta_interna(ins.args[0])
                            and ins.args[0] not in usadas)]
        return antes - len(lista)
