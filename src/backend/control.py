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

Try/catch: el comentario `# try <catch>` apila un manejador en
`__pila_try` (`.space 96`, frames de 12 bytes: catch, $fp, $sp; el tope está en
la palabra `__pila_try_tope`). Un `goto` que sale del cuerpo del try (o un
`return`) lo desapila. Un error (división por cero, o de la parte 3 con
`__error_indice`/`__error_null`/`__error_objeto_null`) salta a su rutina, que
carga el mensaje y salta a `__lanzar`: si hay catch, desapila el frame, restaura
$fp/$sp y salta al catch; si no, imprime la excepción no atrapada y termina.
"""

import tac as T
from programa_mips import etiqueta_fin


# ----------------------------------------------------------------------
# Pila de try / catch (`__pila_try: .space 96`, frames de 12 bytes:
# catch, $fp, $sp). El tope vive en memoria (`__pila_try_tope`), no en un
# registro: así no lo pisan las funciones anidadas (que pasan el enlace de
# acceso en $v1) ni el asignador. Solo se usan $a0/$a1, que no son asignables.
#
# Ciclo de vida de un frame:
#   # try Lk        -> push
#   goto que sale del cuerpo del try (el `goto L_fin` antes de `Lk:`, un
#   break/continue o un return) -> pop de los try que abandona
#   error           -> __lanzar hace el pop y salta al catch (el catch ya corre
#                      sin su frame: un error dentro del catch va al try externo)
# ----------------------------------------------------------------------

def _pila_push(traductor, catch_label) -> None:
    mips = traductor.mips
    mips.emitir("lw", "$a0", "__pila_try_tope", comentario=f"try {catch_label}")
    mips.emitir("la", "$a1", catch_label)
    mips.emitir("sw", "$a1", "0($a0)")
    mips.emitir("sw", "$fp", "4($a0)")
    mips.emitir("sw", "$sp", "8($a0)")
    mips.emitir("addiu", "$a0", "$a0", 12)
    mips.emitir("sw", "$a0", "__pila_try_tope")


def _pila_pop(traductor, cantidad=1) -> None:
    """Saca `cantidad` frames del tope (se sale de esos try sin error)."""
    if cantidad <= 0:
        return
    mips = traductor.mips
    mips.emitir("lw", "$a0", "__pila_try_tope", comentario="salir del try")
    mips.emitir("addiu", "$a0", "$a0", -12 * cantidad)
    mips.emitir("sw", "$a0", "__pila_try_tope")


def _trys_abiertos(unidad, pos) -> int:
    """Cuántos try tienen su cuerpo abierto en la posición `pos` de la unidad:
    el `# try Lk` está antes y la etiqueta del catch `Lk:` todavía no."""
    instrucciones = unidad.instrucciones
    abiertos = 0
    for i, (_, c) in enumerate(instrucciones[:pos]):
        if c.op == T.COMENTARIO and isinstance(c.arg1, str):
            partes = c.arg1.split()
            if len(partes) == 2 and partes[0] == "try":
                catch = partes[1]
                cierre = next((j for j, (_, d) in enumerate(instrucciones)
                               if d.op == T.ETIQUETA and d.arg1 == catch), len(instrucciones))
                if i < pos < cierre:
                    abiertos += 1
    return abiertos


def _posicion_etiqueta(unidad, etiqueta):
    for j, (_, c) in enumerate(unidad.instrucciones):
        if c.op == T.ETIQUETA and c.arg1 == etiqueta:
            return j
    return None


def _comentario(traductor, c) -> None:
    texto = c.arg1
    if isinstance(texto, str) and texto.startswith("try "):
        _pila_push(traductor, texto[len("try "):].strip())
    else:
        traductor.mips.comentario(texto)


def _profundidad_trys(traductor) -> int:
    """Cantidad de try abiertos en la posición actual: un `return` dentro de
    un try debe desarmar la pila."""
    if traductor.unidad is None:
        return 0
    return _trys_abiertos(traductor.unidad, traductor.pos)


def _retornar(traductor, c) -> None:
    _pila_pop(traductor, _profundidad_trys(traductor))
    if c.arg1 is not None:
        traductor.cargar_en("$v0", c.arg1)
    traductor.mips.emitir("j", etiqueta_fin(traductor.unidad.nombre))


def _antes_de_dividir(traductor, divisor) -> None:
    traductor.mips.emitir("beqz", divisor, "__error_division")


def _lanzar(programa) -> None:
    """Rutina __lanzar ($a0 = mensaje): si la pila no está vacía saca el frame
    del try más interno, restaura $fp/$sp y salta a su catch; si está vacía,
    imprime la excepción no atrapada y termina."""
    programa.etiqueta("__lanzar")
    programa.emitir("lw", "$a1", "__pila_try_tope")
    programa.emitir("la", "$v0", "__pila_try")
    programa.emitir("beq", "$a1", "$v0", "__lanzar_fin")
    programa.emitir("addiu", "$a1", "$a1", -12)
    programa.emitir("sw", "$a1", "__pila_try_tope")
    programa.emitir("lw", "$v0", "0($a1)")
    programa.emitir("lw", "$fp", "4($a1)")
    programa.emitir("lw", "$sp", "8($a1)")
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
    """Un goto que sale del cuerpo de uno o más try (fin normal del try,
    break, continue) saca sus frames antes de saltar."""
    unidad = traductor.unidad
    destino = _posicion_etiqueta(unidad, c.resultado)
    if destino is not None:
        _pila_pop(traductor, _trys_abiertos(unidad, traductor.pos)
                  - _trys_abiertos(unidad, destino))
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
    traductor.mips.datos_extra.append("__pila_try_tope: .word __pila_try")
    traductor.mips.datos_extra.append('__msg_error_division: .asciiz "division por cero"')
    traductor.mips.datos_extra.append('__msg_error_indice: .asciiz "indice fuera de rango"')
    traductor.mips.datos_extra.append('__msg_error_null: .asciiz "arreglo nulo"')
