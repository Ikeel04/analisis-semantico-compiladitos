"""
Punto de entrada del backend: TAC -> ensamblador MIPS32.

    from backend import generar_ensamblador

    resultado = generar_ensamblador(programa_tac, tabla, resumen)
    resultado.asm                # ensamblador final, listo para MARS
    resultado.marcos             # MarcoMIPS por función
    resultado.traza              # TAC -> MIPS + descriptor de registros

PRECONDICIÓN: solo se llama cuando hubo TAC, es decir, cuando el programa no
tuvo ningún error (la compuerta está en pipeline.analizar_codigo).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field

_AQUI = os.path.dirname(os.path.abspath(__file__))
if _AQUI not in sys.path:
    sys.path.insert(0, _AQUI)

from traductor import TraductorMIPS


@dataclass
class ResultadoBackend:
    asm: str = ""                        # el que se descarga y se ejecuta
    asm_sin_optimizar: str = ""
    instrucciones_antes: int = 0
    instrucciones_despues: int = 0
    mirilla: dict = field(default_factory=dict)    # regla -> veces aplicada
    traza: list = field(default_factory=list)
    marcos: dict = field(default_factory=dict)
    registros: dict = field(default_factory=dict)  # unidad -> estadísticas
    pendientes: list = field(default_factory=list)

    def filas_marcos(self) -> list[dict]:
        filas = []
        for marco in self.marcos.values():
            filas += marco.filas_para_ide()
        return filas

    def marcos_texto(self) -> str:
        return "\n\n".join(m.describe() for m in self.marcos.values())

    def filas_registros(self) -> list[dict]:
        return [{"Unidad": unidad, **estadisticas}
                for unidad, estadisticas in self.registros.items()]


def _contar(instrucciones) -> int:
    return sum(1 for i in instrucciones if not i.es_etiqueta and not i.es_comentario)


def generar_ensamblador(programa_tac, tabla, resumen) -> ResultadoBackend:
    traductor = TraductorMIPS(programa_tac, tabla, resumen)
    mips = traductor.traducir()

    resultado = ResultadoBackend(
        asm_sin_optimizar=mips.como_texto(),
        instrucciones_antes=_contar(mips.texto),
        traza=traductor.traza,
        marcos=traductor.marcos,
        registros=traductor.estadisticas_registros,
        pendientes=traductor.pendientes,
    )
    resultado.asm = resultado.asm_sin_optimizar
    resultado.instrucciones_despues = resultado.instrucciones_antes
    return resultado
