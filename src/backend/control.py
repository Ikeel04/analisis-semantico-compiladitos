"""
Manejadores de saltos y control de flujo (parte 2).

`registrar(traductor)` agrega a `traductor.manejadores` los cuádruplos de saltos
y etiquetas que la parte 1 no resuelve. El traductor ya decide cuándo guardar lo
sucio y olvidar los registros al salir de un bloque, así que los manejadores
acá solo emiten la instrucción MIPS.

| TAC                | MIPS                  |
|--------------------|-----------------------|
| `goto L`           | `j L`                 |
| `if t goto L`      | `bnez t, L`           |
| `ifFalse t goto L` | `beqz t, L`           |
| `L:`               | `L:`                  |

Antes de emitir el salto el traductor ya cerró el bloque actual (guardando en
memoria los temporales sucios que quedaban vivos), así que el `beqz`/`bnez` ve un
registro limpio.
"""

import tac as T


def registrar(traductor) -> None:
    mips = traductor.mips

    def etiqueta(c):
        mips.etiqueta(c.arg1)

    def salto(c):
        mips.emitir("j", c.resultado)

    def saltar_si(c):
        mips.emitir("bnez", traductor.registro_de(c.arg1), c.resultado)

    def saltar_si_falso(c):
        mips.emitir("beqz", traductor.registro_de(c.arg1), c.resultado)

    traductor.manejadores[T.ETIQUETA] = etiqueta
    traductor.manejadores[T.SALTAR] = salto
    traductor.manejadores[T.SALTAR_SI] = saltar_si
    traductor.manejadores[T.SALTAR_SI_FALSO] = saltar_si_falso
