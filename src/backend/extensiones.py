"""
Extensiones del traductor MIPS (partes 2 y 3).

Cada parte escribe su propio módulo (por ejemplo `control.py` o `datos.py`)
con una función `registrar(traductor)` que agrega manejadores o reemplaza los
puntos de extensión, y la anota en EXTENSIONES. Así nadie tiene que editar
traductor.py y no hay conflictos al juntar ramas:

    # src/backend/control.py
    import tac as T

    def registrar(traductor):
        traductor.manejadores[T.ETIQUETA] = lambda c: _etiqueta(traductor, c)
        traductor.antes_de_dividir = lambda divisor: ...

    # aquí abajo
    from control import registrar as registrar_control
    EXTENSIONES = [registrar_control]

Rutinas de soporte (concatenar cadenas, reservar memoria, lanzar una
excepción…): un manejador llama a `traductor.mips.usar_rutina(nombre, emisor)`
y el traductor emite cada rutina una sola vez al final del segmento de texto.
`emisor(programa)` recibe el ProgramaMIPS y emite la rutina completa, con su
etiqueta. Las etiquetas internas de una rutina deben empezar con `__L` (la
mirilla puede borrarlas si quedan sin uso).
"""

from control import registrar as registrar_control
from datos import registrar as registrar_datos

EXTENSIONES: list = [registrar_control, registrar_datos]


def aplicar(traductor) -> None:
    for registrar in EXTENSIONES:
        registrar(traductor)
