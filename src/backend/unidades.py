"""
Separación del TAC en unidades de traducción y bloques básicos.

El TAC intercala las funciones con el código global, y una función anidada
aparece en medio del cuerpo de la que la contiene. El ensamblador necesita
cada rutina contigua, así que aquí se separa en `main` (todo el código global)
y una unidad por cada `function … endfunction`.
"""

from __future__ import annotations

import re
import sys
import os
from dataclasses import dataclass, field

_SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_INTERMEDIO = os.path.join(_SRC, "intermediate")
if _INTERMEDIO not in sys.path:
    sys.path.insert(0, _INTERMEDIO)

import tac as T

UNIDAD_PRINCIPAL = "main"

_TEMPORAL = re.compile(r"^t\d+$")
_DIRECCION = re.compile(r"^(global|fp)\+\d+$")


def es_temporal(operando) -> bool:
    return isinstance(operando, str) and bool(_TEMPORAL.match(operando))


def es_direccion(operando) -> bool:
    """Variables del programa con dirección propia (no los atributos obj+N,
    que viven dentro de un objeto y se acceden a través de 'this')."""
    return isinstance(operando, str) and bool(_DIRECCION.match(operando))


def es_nombre(operando) -> bool:
    """Nombres que el asignador puede guardar en registros."""
    return es_temporal(operando) or es_direccion(operando)


def indice_temporal(nombre: str) -> int:
    return int(nombre[1:])


@dataclass
class UnidadTAC:
    nombre: str
    # (índice en el ProgramaTAC original, cuádruplo)
    instrucciones: list = field(default_factory=list)

    @property
    def es_principal(self) -> bool:
        return self.nombre == UNIDAD_PRINCIPAL

    def max_temporal(self) -> int:
        """Índice más alto de temporal usado: cuántas celdas de temporal reservar."""
        maximo = 0
        for _, c in self.instrucciones:
            for campo in (c.arg1, c.arg2, c.resultado):
                if es_temporal(campo):
                    maximo = max(maximo, indice_temporal(campo))
        return maximo


def separar_unidades(programa) -> list[UnidadTAC]:
    """Devuelve [main, f1, f2, ...] con las funciones en orden de aparición."""
    principal = UnidadTAC(UNIDAD_PRINCIPAL)
    unidades = [principal]
    pila = [principal]
    for indice, c in enumerate(programa):
        if c.op == T.INICIO_FUNCION:
            unidad = UnidadTAC(c.arg1)
            unidades.append(unidad)
            pila.append(unidad)
        elif c.op == T.FIN_FUNCION:
            pila.pop()
        else:
            pila[-1].instrucciones.append((indice, c))
    return unidades


# ----------------------------------------------------------------------
# Usos y definiciones de cada cuádruplo
# ----------------------------------------------------------------------

_DEFINEN_RESULTADO = (T.BINARIAS | T.UNARIAS |
                      {T.ASIGNAR, T.LLAMAR, T.NUEVO_ARREGLO, T.LEER_INDICE,
                       T.NUEVO, T.LEER_CAMPO, T.LONGITUD})


def usos(c) -> list:
    """Operandos que el cuádruplo lee."""
    if c.op in (T.ETIQUETA, T.SALTAR, T.COMENTARIO, T.INICIO_FUNCION,
                T.FIN_FUNCION, T.NUEVO):
        return []
    if c.op == T.LLAMAR:
        return []
    if c.op in (T.ESCRIBIR_INDICE, T.ESCRIBIR_CAMPO):
        # (op, índice/campo, valor, arreglo/objeto): el destino también se lee.
        leidos = [c.arg2, c.resultado]
        if c.op == T.ESCRIBIR_INDICE:
            leidos.insert(0, c.arg1)
        return leidos
    if c.op == T.LEER_CAMPO:
        return [c.arg1]
    return [a for a in (c.arg1, c.arg2) if a is not None]


def definicion(c):
    """Nombre que el cuádruplo escribe, o None."""
    if c.op in _DEFINEN_RESULTADO and c.resultado is not None:
        return c.resultado
    return None


# ----------------------------------------------------------------------
# Bloques básicos
# ----------------------------------------------------------------------

TERMINAN_BLOQUE = {T.SALTAR, T.SALTAR_SI, T.SALTAR_SI_FALSO, T.RETORNAR}


@dataclass
class Bloque:
    numero: int
    posiciones: list = field(default_factory=list)   # índices dentro de la unidad
    etiqueta: str | None = None
    sucesores: list = field(default_factory=list)


def bloques_basicos(unidad: UnidadTAC) -> list[Bloque]:
    """Líderes: la primera instrucción, cada etiqueta y lo que sigue a un salto
    o a un return. Una llamada NO parte el bloque: el traductor maneja la
    frontera de registros dentro del propio `call`."""
    bloques: list[Bloque] = []
    actual = None
    for pos, (_, c) in enumerate(unidad.instrucciones):
        if actual is None or c.op == T.ETIQUETA:
            if actual is None or actual.posiciones:
                actual = Bloque(len(bloques))
                bloques.append(actual)
            if c.op == T.ETIQUETA:
                actual.etiqueta = c.arg1
        actual.posiciones.append(pos)
        if c.op in TERMINAN_BLOQUE:
            actual = None

    por_etiqueta = {b.etiqueta: b.numero for b in bloques if b.etiqueta}
    for b in bloques:
        _, ultimo = unidad.instrucciones[b.posiciones[-1]]
        siguiente = b.numero + 1 if b.numero + 1 < len(bloques) else None
        if ultimo.op == T.SALTAR:
            destinos = [por_etiqueta.get(ultimo.resultado)]
        elif ultimo.op in (T.SALTAR_SI, T.SALTAR_SI_FALSO):
            destinos = [por_etiqueta.get(ultimo.resultado), siguiente]
        elif ultimo.op == T.RETORNAR:
            destinos = []
        else:
            destinos = [siguiente]
        b.sucesores = [d for d in destinos if d is not None]
    return bloques
