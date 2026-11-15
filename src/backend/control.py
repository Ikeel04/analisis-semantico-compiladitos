"""
Manejadores de saltos, control de flujo y try/catch (parte 2).

`registrar(traductor)` agrega a `traductor.manejadores` los cuádruplos de saltos,
etiquetas, comentarios (try/catch), retornos (desbalanceo de la pila) y reemplaza
el punto de extensión `antes_de_dividir` (división/módulo por cero).

| TAC                | MIPS                  |
|--------------------|-----------------------|
| `goto L`           | `j L`                 |
| `if t goto L`      | `bnez t, L`           |
| `ifFalse t goto L` | `beqz t, L`           |
| `L:`               | `L:`                  |

Antes de emitir el salto el traductor ya cerró el bloque actual (guardando en
memoria los temporales sucios que quedaban vivos), así que el `beqz`/`bnez` ve un
registro limpio.

Try/catch: los comentarios `# try <catch>` / `# fin try <catch>` abren y cierran
la pila de manejadores (`__pila_try: .space 96`, frames de 12 bytes: catch, $fp,
$sp; puntero base en $v1). Un error (división por cero, o de la parte 3 con
`__error_indice`/`__error_null`) salta a su rutina que carga el mensaje y lanza a
`__lanzar`, que si hay catch restaura $fp/$sp y salta al catch, si no imprime la
excepción no atrapada y termina.
"""

import tac as T
from programa_mips import etiqueta_fin


# ----------------------------------------------------------------------
# Pila de try / catch (`__pila_try: .space 96`, frames de 12 bytes:
# catch, $fp, $sp). Puntero base en $v1 (no es un registro asignable).
# ----------------------------------------------------------------------

def _pila_push(traductor, catch_label) -> None:
    mips = traductor.mips
    mips.emitir("la", "$v1", "__pila_try")
    mips.emitir("la", "$t0", catch_label)
    mips.emitir("sw", "$t0", "0($v1)")
    mips.emitir("sw", "$fp", "4($v1)")
    mips.emitir("sw", "$sp", "8($v1)")
    mips.emitir("addi", "$v1", "$v1", 12)


def _pila_pop(traductor) -> None:
    """Saca el tope de la pila (descarta el frame del manejador que se cierra)."""
    traductor.mips.emitir("addi", "$v1", "$v1", -12)


def _comentario(traductor, c) -> None:
    texto = c.arg1
    if isinstance(texto, str):
        if texto.startswith("try "):
            _pila_push(traductor, texto[len("try "):].strip())
        elif texto.startswith("fin try "):
            _pila_pop(traductor)
    traductor.mips.comentario(texto)


def _profundidad_trys(traductor) -> int:
    """Cantidad de try/catch abiertos en el scope en curso (hasta la posición
    actual): los `return` dentro de un try deben desarmar la pila."""
    unidad = traductor.unidad
    profundidad = 0
    if unidad is None:
        return 0
    for _, c in reversed(unidad.instrucciones[:traductor.pos]):
        if c.op == T.COMENTARIO and isinstance(c.arg1, str):
            partes = c.arg1.split()
            if len(partes) == 2 and partes[0] == "try":
                profundidad += 1
            elif len(partes) == 3 and partes[0] == "fin":
                profundidad -= 1
    return max(profundidad, 0)


def _retornar(traductor, c) -> None:
    for _ in range(_profundidad_trys(traductor)):
        _pila_pop(traductor)
    if c.arg1 is not None:
        traductor.cargar_en("$v0", c.arg1)
    traductor.mips.emitir("j", etiqueta_fin(traductor.unidad.nombre))


def _antes_de_dividir(traductor, divisor) -> None:
    traductor.mips.emitir("beqz", divisor, "__error_division")


def _lanzar(programa) -> None:
    """Rutina __lanzar: si la pila no está vacía restaura $fp/$sp y salta al
    catch del frame que abrió la excepción; si está vacía, imprime la excepción
    no atrapada y termina."""
    programa.etiqueta("__lanzar")
    programa.emitir("la", "$v0", "__pila_try")
    programa.emitir("subu", "$t0", "$v1", "$v0")
    programa.emitir("beq", "$t0", "$zero", "__lanzar_fin")
    programa.emitir("addi", "$v1", "$v1", -12)
    programa.emitir("lw", "$v0", "0($v1)")
    programa.emitir("lw", "$t1", "4($v1)")
    programa.emitir("lw", "$t2", "8($v1)")
    programa.emitir("addi", "$v1", "$v1", 12)
    programa.emitir("move", "$fp", "$t1")
    programa.emitir("move", "$sp", "$t2")
    programa.emitir("jr", "$v0")
    programa.etiqueta("__lanzar_fin")
    programa.emitir("li", "$v0", 4)
    programa.emitir("syscall")
    programa.emitir("li", "$a0", 10)
    programa.emitir("li", "$v0", 11)
    programa.emitir("syscall")
    programa.emitir("li", "$v0", 10)
    programa.emitir("syscall")


def _error_rutina(programa, nombre: str, mensaje: str) -> None:
    programa.etiqueta(nombre)
    programa.emitir("la", "$a0", mensaje)
    programa.emitir("jal", "__lanzar")


def _etiqueta(traductor, c) -> None:
    traductor.mips.etiqueta(c.arg1)


def _salto(traductor, c) -> None:
    traductor.mips.emitir("j", c.resultado)


def _saltar_si(traductor, c) -> None:
    traductor.mips.emitir("bnez", traductor.registro_de(c.arg1), c.resultado)


def _saltar_si_falso(traductor, c) -> None:
    traductor.mips.emitir("beqz", traductor.registro_de(c.arg1), c.resultado)


def registrar(traductor) -> None:
    traductor.manejadores[T.ETIQUETA] = lambda c: _etiqueta(traductor, c)
    traductor.manejadores[T.SALTAR] = lambda c: _salto(traductor, c)
    traductor.manejadores[T.SALTAR_SI] = lambda c: _saltar_si(traductor, c)
    traductor.manejadores[T.SALTAR_SI_FALSO] = lambda c: _saltar_si_falso(traductor, c)
    traductor.manejadores[T.COMENTARIO] = lambda c: _comentario(traductor, c)
    traductor.manejadores[T.RETORNAR] = lambda c: _retornar(traductor, c)
    traductor.antes_de_dividir = lambda divisor: _antes_de_dividir(traductor, divisor)
    traductor.mips.usar_rutina("__lanzar", _lanzar)
    for nombre, mensaje in (
        ("__error_division", "__msg_error_division"),
        ("__error_indice", "__msg_error_indice"),
        ("__error_null", "__msg_error_null"),
    ):
        traductor.mips.usar_rutina(
            nombre, lambda programa, n=nombre, m=mensaje: _error_rutina(programa, n, m))
    traductor.mips.datos_extra.append("        .align 4")
    traductor.mips.datos_extra.append("__pila_try: .space 96")
    traductor.mips.datos_extra.append('__msg_error_division: .asciiz "division por cero"')
    traductor.mips.datos_extra.append('__msg_error_indice: .asciiz "indice fuera de rango"')
    traductor.mips.datos_extra.append('__msg_error_null: .asciiz "arreglo nulo"')
