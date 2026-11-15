"""
Registros de activación en la pila de MIPS.

Toma el RegistroActivacion que calculó memoria.py (parámetros y locales con su
desplazamiento) y le agrega lo que solo se sabe al generar ensamblador: las
celdas de los temporales que usa la función, la celda del receptor en los
métodos y el tamaño final del marco. También emite prólogo y epílogo.

Disposición (desplazamientos desde $fp, que apunta a la base del marco):

    $fp + 0        enlace de control (el $fp de quien llamó)
    $fp + 8        dirección de retorno
    $fp + 16       parámetros y locales (offsets de memoria.py)
    $fp + base_t   temporales, 8 bytes cada uno
    $fp + this     receptor (solo métodos)
    $fp + S + ...  argumentos apilados por quien llamó
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field

_SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_INTERMEDIO = os.path.join(_SRC, "intermediate")
if _INTERMEDIO not in sys.path:
    sys.path.insert(0, _INTERMEDIO)

from memoria import (
    INICIO_PARAMETROS,
    OFFSET_DIRECCION_RETORNO,
    OFFSET_ENLACE_CONTROL,
    TAMANO_PALABRA,
)
from programa_mips import etiqueta_fin, etiqueta_funcion
from tipos import es_byte

TAMANO_ARGUMENTO = 4          # cada `param` apila una palabra de MIPS32


def _alinear_a(valor: int, multiplo: int) -> int:
    resto = valor % multiplo
    return valor if resto == 0 else valor + multiplo - resto


def es_metodo(nombre_cualificado: str, clases) -> bool:
    """'Animal.hablar' y 'Cuenta.__atributos' reciben el objeto como primer
    argumento; 'contador.interno' (función anidada) no."""
    if "." not in nombre_cualificado:
        return False
    return nombre_cualificado.rsplit(".", 1)[0] in clases


@dataclass
class Celda:
    offset: int
    nombre: str
    detalle: str


@dataclass
class MarcoMIPS:
    nombre: str
    parametros: list = field(default_factory=list)   # [(offset, nombre, tipo)]
    locales: list = field(default_factory=list)
    base_temporales: int = INICIO_PARAMETROS
    cantidad_temporales: int = 0
    offset_receptor: int | None = None
    tamano: int = INICIO_PARAMETROS
    offset_enlace_acceso: int | None = None   # función anidada: celda del enlace

    @property
    def es_metodo(self) -> bool:
        return self.offset_receptor is not None

    @property
    def es_funcion_anidada(self) -> bool:
        """Función declarada dentro de otra (closure): le falta el enlace de
        acceso para resolver las variables capturadas."""
        return self.offset_enlace_acceso is not None

    @property
    def argumentos(self) -> int:
        """Palabras que apila quien llama: receptor (si hay) + parámetros."""
        return len(self.parametros) + (1 if self.es_metodo else 0)

    def offset_argumento(self, indice: int) -> int:
        """Dónde quedó el argumento `indice` (0 = el primero apilado), visto
        desde el $fp del llamado: el primero apilado es el más profundo."""
        return self.tamano + TAMANO_ARGUMENTO * (self.argumentos - 1 - indice)

    def offset_temporal(self, k: int) -> int:
        return self.base_temporales + TAMANO_PALABRA * (k - 1)

    def celdas(self) -> list[Celda]:
        celdas = [Celda(OFFSET_ENLACE_CONTROL, "enlace de control", "$fp anterior"),
                  Celda(OFFSET_DIRECCION_RETORNO, "dirección de retorno", "$ra")]
        for offset, nombre, tipo in self.parametros:
            celdas.append(Celda(offset, nombre, f"parámetro · {tipo}"))
        for offset, nombre, tipo in self.locales:
            celdas.append(Celda(offset, nombre, f"local · {tipo}"))
        for k in range(1, self.cantidad_temporales + 1):
            celdas.append(Celda(self.offset_temporal(k), f"t{k}", "temporal"))
        if self.es_funcion_anidada:
            celdas.append(Celda(self.offset_enlace_acceso, "enlace de acceso",
                                 "frame de la función que captura"))
        if self.es_metodo:
            celdas.append(Celda(self.offset_receptor, "this", "receptor"))
        for i in range(self.argumentos):
            celdas.append(Celda(self.offset_argumento(i), f"argumento {i}",
                                "apilado por quien llama"))
        return sorted(celdas, key=lambda c: c.offset)

    def filas_para_ide(self) -> list[dict]:
        return [{"Función": self.nombre, "Desplazamiento": f"{c.offset}($fp)",
                 "Contenido": c.nombre, "Detalle": c.detalle}
                for c in self.celdas()]

    def describe(self) -> str:
        lineas = [f"marco de '{self.nombre}' ({self.tamano} bytes, "
                  f"{self.argumentos} argumento(s) apilado(s))"]
        for c in self.celdas():
            lineas.append(f"  {c.offset:>4}($fp)  {c.nombre} ({c.detalle})")
        return "\n".join(lineas)


def construir_marco(nombre: str, registro, temporales: int, metodo: bool,
                    anidada: bool = False) -> MarcoMIPS:
    """`registro` puede ser None: las funciones generadas (Clase.__atributos)
    no tienen registro en memoria.py, pero igual necesitan marco."""
    marco = MarcoMIPS(nombre)
    fin_datos = INICIO_PARAMETROS
    if registro is not None:
        marco.parametros = [(s.offset, s.name, s.type) for s in registro.parametros]
        marco.locales = [(s.offset, s.name, s.type) for s in registro.locales]
        fin_datos = registro.offset_temporales
    marco.base_temporales = _alinear_a(fin_datos, 4)
    marco.cantidad_temporales = temporales
    fin = marco.base_temporales + TAMANO_PALABRA * temporales
    if metodo:
        marco.offset_receptor = _alinear_a(fin, 4)
        fin = marco.offset_receptor + TAMANO_PALABRA
    if anidada:
        marco.offset_enlace_acceso = _alinear_a(fin, 4)
        fin = marco.offset_enlace_acceso + TAMANO_PALABRA
    marco.tamano = _alinear_a(fin, 8)
    return marco


def emitir_prologo(programa, marco: MarcoMIPS) -> None:
    programa.etiqueta(etiqueta_funcion(marco.nombre))
    programa.emitir("addiu", "$sp", "$sp", -marco.tamano,
                    comentario=f"reservar marco ({marco.tamano} bytes)")
    programa.emitir("sw", "$fp", f"{OFFSET_ENLACE_CONTROL}($sp)",
                    comentario="enlace de control")
    programa.emitir("sw", "$ra", f"{OFFSET_DIRECCION_RETORNO}($sp)",
                    comentario="dirección de retorno")
    programa.emitir("move", "$fp", "$sp")
    indice = 0
    if marco.es_metodo:
        programa.emitir("lw", "$a2", f"{marco.offset_argumento(0)}($fp)")
        programa.emitir("sw", "$a2", f"{marco.offset_receptor}($fp)",
                        comentario="this")
        indice = 1
    for offset, nombre, tipo in marco.parametros:
        programa.emitir("lw", "$a2", f"{marco.offset_argumento(indice)}($fp)")
        programa.emitir("sb" if es_byte(tipo) else "sw", "$a2", f"{offset}($fp)",
                        comentario=f"parámetro {nombre}")
        indice += 1
    if marco.es_funcion_anidada:
        # Función anidada (closure): guarda el enlace de acceso recibido ($v1)
        # para resolver las variables capturadas de la función que la contiene.
        programa.emitir("sw", "$v1", f"{marco.offset_enlace_acceso}($fp)",
                        comentario="enlace de acceso")


def emitir_epilogo(programa, marco: MarcoMIPS) -> None:
    programa.etiqueta(etiqueta_fin(marco.nombre))
    programa.emitir("move", "$sp", "$fp")
    programa.emitir("lw", "$ra", f"{OFFSET_DIRECCION_RETORNO}($sp)")
    programa.emitir("lw", "$fp", f"{OFFSET_ENLACE_CONTROL}($sp)")
    programa.emitir("addiu", "$sp", "$sp", marco.tamano,
                    comentario="liberar marco")
    programa.emitir("jr", "$ra")
