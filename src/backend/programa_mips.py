"""
Representación del ensamblador MIPS que produce el backend.

Cada instrucción es un objeto (no una cadena) para que el optimizador de
mirilla pueda inspeccionar operación y operandos sin volver a parsear texto.
El diseño está en docs/DISENO_MIPS.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

ETIQUETA = "label"
COMENTARIO = "#"

SALTOS_INCONDICIONALES = {"j", "b", "jr"}
# Saltos condicionales: posición del operando que es la etiqueta destino.
SALTOS_CONDICIONALES = {
    "beq": 2, "bne": 2, "blt": 2, "ble": 2, "bgt": 2, "bge": 2,
    "beqz": 1, "bnez": 1, "bltz": 1, "blez": 1, "bgtz": 1, "bgez": 1,
}
SALTO_INVERSO = {
    "beq": "bne", "bne": "beq", "blt": "bge", "bge": "blt",
    "ble": "bgt", "bgt": "ble", "beqz": "bnez", "bnez": "beqz",
    "bltz": "bgez", "bgez": "bltz", "blez": "bgtz", "bgtz": "blez",
}


@dataclass
class Instr:
    """Una línea del segmento de texto: instrucción, etiqueta o comentario."""

    op: str
    args: tuple = ()
    comentario: str = ""

    def __str__(self) -> str:
        if self.op == ETIQUETA:
            return f"{self.args[0]}:"
        if self.op == COMENTARIO:
            return f"        # {self.args[0]}"
        texto = f"        {self.op:<7} {', '.join(self.args)}".rstrip()
        if self.comentario:
            texto = f"{texto:<40}# {self.comentario}"
        return texto

    @property
    def es_etiqueta(self) -> bool:
        return self.op == ETIQUETA

    @property
    def es_comentario(self) -> bool:
        return self.op == COMENTARIO

    @property
    def es_salto_incondicional(self) -> bool:
        return self.op in SALTOS_INCONDICIONALES

    @property
    def es_salto_condicional(self) -> bool:
        return self.op in SALTOS_CONDICIONALES

    @property
    def destino(self) -> str | None:
        """Etiqueta a la que salta, o None si no es un salto a etiqueta."""
        if self.op in ("j", "b"):
            return self.args[0]
        if self.op in SALTOS_CONDICIONALES:
            return self.args[SALTOS_CONDICIONALES[self.op]]
        return None

    def con_destino(self, etiqueta: str) -> "Instr":
        args = list(self.args)
        if self.op in ("j", "b"):
            args[0] = etiqueta
        else:
            args[SALTOS_CONDICIONALES[self.op]] = etiqueta
        return Instr(self.op, tuple(args), self.comentario)


@dataclass
class ProgramaMIPS:
    """Secciones .data y .text del programa generado."""

    texto: list[Instr] = field(default_factory=list)
    tamano_globales: int = 0
    cadenas: dict = field(default_factory=dict)   # literal (con comillas) -> etiqueta

    def emitir(self, op: str, *args, comentario: str = "") -> Instr:
        instr = Instr(op, tuple(str(a) for a in args), comentario)
        self.texto.append(instr)
        return instr

    def etiqueta(self, nombre: str) -> Instr:
        return self.emitir(ETIQUETA, nombre)

    def comentario(self, texto: str) -> Instr:
        return self.emitir(COMENTARIO, texto)

    def cadena(self, literal: str) -> str:
        """Etiqueta de .data para un literal de cadena (se reutiliza si se repite)."""
        if literal not in self.cadenas:
            self.cadenas[literal] = f"__str_{len(self.cadenas)}"
        return self.cadenas[literal]

    def seccion_datos(self) -> list[str]:
        lineas = ["        .data",
                  "        .align 3",
                  f"__globales: .space {max(self.tamano_globales, 8)}"]
        # El literal del TAC ya trae sus comillas, y .asciiz acepta las mismas
        # secuencias de escape que Compiscript (\n, \t, \\").
        for literal, etiqueta in self.cadenas.items():
            lineas.append(f"{etiqueta}: .asciiz {literal}")
        lineas += ['__verdadero: .asciiz "true"',
                   '__falso: .asciiz "false"']
        return lineas

    def como_texto(self, texto: list[Instr] | None = None) -> str:
        cuerpo = self.texto if texto is None else texto
        lineas = self.seccion_datos()
        lineas += ["", "        .text", "        .globl main"]
        lineas += [str(i) for i in cuerpo]
        return "\n".join(lineas) + "\n"


_NOMBRE_INVALIDO = re.compile(r"[^A-Za-z0-9_]")


def etiqueta_funcion(nombre_cualificado: str) -> str:
    """'Animal.hablar' -> 'fn_Animal__hablar' (los puntos no son portables)."""
    return "fn_" + _NOMBRE_INVALIDO.sub("_", nombre_cualificado.replace(".", "__"))


def etiqueta_fin(nombre_cualificado: str) -> str:
    return etiqueta_funcion(nombre_cualificado) + "_fin"
