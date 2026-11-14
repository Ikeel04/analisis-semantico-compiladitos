# Diseño del backend: de TAC a ensamblador MIPS32

Este documento fija cómo se traduce el código de tres direcciones (TAC) a
ensamblador. Es el contrato del equipo para la última entrega: la parte 1
construye la base (registros, marcos, expresiones, mirilla e interfaz) y las
partes 2 y 3 llenan los manejadores que faltan (control de flujo, try/catch,
arreglos, clases y cadenas) sin tocar esa base.

El ensamblador **se genera a partir del TAC** del proyecto anterior: el backend
no vuelve a recorrer el árbol de ANTLR. Recibe el `ProgramaTAC`, la tabla de
símbolos y el `ResumenMemoria` que ya produce `memoria.py`.

---

## 1. Arquitectura destino y herramienta

- **MIPS32**, ensamblado y ejecutado en **MARS 4.5** (también corre en SPIM).
- MARS se usa desde consola para verificar los ejemplos:

  ```bash
  java -jar Mars4_5.jar nc programa.asm
  ```

  (`nc` quita el aviso de copyright). Se descarga de
  <https://github.com/dpetersanderson/MARS/releases> y requiere Java 8 o más.
- La salida usa solo las llamadas al sistema comunes a MARS y SPIM:
  `1` (entero), `2` (float), `4` (cadena), `9` (sbrk), `10` (salir) y
  `11` (carácter).

**Por qué MIPS.** Es una arquitectura de carga/almacenamiento con 32 registros
generales: el problema de selección de registros es real (hay que decidir qué
vive en registro y qué en memoria) pero sin las restricciones de x86 (operandos
de dos direcciones, registros especiales para la división). Además MARS muestra
registros y memoria, lo que sirve para demostrar los marcos de activación.

---

## 2. Organización del programa generado

```
        .data
        .align 3
__globales: .space N          # variables globales + temporales del main
__str_0:    .asciiz "hola"    # una etiqueta por literal de cadena
__verdadero: .asciiz "true"
__falso:     .asciiz "false"

        .text
        .globl main
main:
        la    $s7, __globales  # base del área global
        move  $fp, $sp
        <código global>
        li    $v0, 10          # exit
        syscall

fn_suma:                       # una rutina por función del TAC
        <prólogo>
        <cuerpo>
fn_suma_fin:
        <epílogo>
```

El TAC intercala funciones con el código global (y una función anidada aparece
dentro del cuerpo de la que la contiene). `unidades.py` lo separa en
**unidades**: `main` con todo el código global, y una unidad por cada
`function … endfunction`, sin importar el anidamiento.

Los nombres de función se convierten en etiquetas válidas: `Animal.hablar` →
`fn_Animal__hablar`.

---

## 3. Operandos del TAC y dónde viven

| Operando del TAC | Ejemplo | Ubicación en MIPS |
|---|---|---|
| Variable global | `global+16` | `16($s7)` |
| Parámetro o local | `fp+20` | `20($fp)` |
| Temporal del main | `t3` | `__globales + base_t + 8·(3-1)` vía `$s7` |
| Temporal de función | `t3` | `base_t + 8·(3-1)($fp)` |
| Receptor de un método | `this` | celda del receptor en el marco |
| Entero / booleano / null | `42`, `true`, `null` | inmediato (`li`) o `$zero` |
| Float | `2.5` | inmediato con los bits IEEE-754 (`li $a2, 0x40200000`) |
| Cadena | `"hola"` | `la` a la etiqueta en `.data` |
| Atributo dentro de método | `obj+4` | **parte 3** (`4(this)`) |
| Variable capturada | `base` | **parte 2** (enlace de acceso) |

El tamaño de cada dato sale de su tipo (`memoria.tamano_de`): los `boolean`
ocupan un byte y se leen/escriben con `lbu`/`sb`; todo lo demás es una palabra
(`lw`/`sw`). Los `float` se guardan como precisión simple (4 bytes) dentro de
su celda de 8. Las cadenas, arreglos y objetos son punteros de 4 bytes.

`tipos.py` infiere el tipo de cada operando: las direcciones lo toman de la
tabla de símbolos, los literales de su forma, y los temporales del cuádruplo
que los definió (`t1 = a < b` es `boolean`, `t1 = call f` toma el tipo de
retorno de `f`, etc.).

---

## 4. Selección de registros (`registros.py`)

Implementa el algoritmo `getReg` del *Dragon Book* (§8.6) con descriptores:

- **Descriptor de registro**: para cada registro, qué nombres (temporales o
  direcciones) tiene su valor actual.
- **Descriptor de dirección**: para cada nombre, en qué registros está su valor
  y si la copia en memoria está al día.

Registros asignables: `$t0–$t9` y `$s0–$s6` (17). Reservados: `$s7` (base
global), `$fp`, `$sp`, `$ra`, `$v0` (retorno y syscalls), `$a0`/`$a1`
(syscalls), `$a2`/`$a3` (auxiliares para literales y copias de argumentos), `$at`
(ensamblador), `$f4`/`$f6`/`$f12` (operaciones con float).

### Para `x = y op z`

1. **Registro de `y`**: si `y` ya está en un registro, se usa ese. Si no, se
   busca uno libre; si no hay, el que tenga menor costo de desalojo (cantidad
   de valores que habría que guardar en memoria: los que no están al día y
   siguen vivos). Se emite el `lw`.
2. **Registro de `z`**: igual, protegiendo el de `y`.
3. **Registro de `x`**: se reutiliza el de `y` (o `z`) si solo guarda ese
   valor y ya no se usa después —o `x` es el mismo `y`, como en `x = x + 1`—;
   si no, uno libre o el de menor costo.
4. Tras la operación: el registro de `x` solo contiene `x`, y `x` solo está en
   ese registro (la memoria quedó desactualizada: está «sucio»).

### Para la copia `x = y`

No se emite instrucción: `x` se agrega al descriptor del registro de `y`
(dos nombres comparten registro). Si `y` es un literal, se carga en el registro
de `x`.

### Información de vida

`registros.py` no decide solo: el traductor le da, para cada instrucción, qué
nombres siguen vivos después. Se calcula con:

1. **Bloques básicos** de cada unidad (líderes: primera instrucción, etiquetas
   y la instrucción que sigue a un salto o `return`).
2. **Análisis de vida de temporales** entre bloques (flujo de datos hacia
   atrás, iterado hasta punto fijo): un temporal está vivo a la salida de un
   bloque si algún sucesor lo usa antes de redefinirlo. Así el índice de un
   `foreach` o el sujeto de un `switch` sobreviven al salto, y los demás
   temporales no se guardan en memoria al terminar el bloque.
3. Dentro del bloque, un recorrido hacia atrás marca el siguiente uso de cada
   nombre.

Las **variables del programa** se consideran siempre vivas a la salida del
bloque (pueden leerse en otro bloque o en otra función), así que se guardan si
están sucias.

### Fronteras

| Momento | Qué hace el asignador |
|---|---|
| Fin de bloque (antes de `goto`, `if`, `ifFalse`, `return` o de caer a una etiqueta) | guarda los valores sucios vivos |
| Inicio de bloque (después de una etiqueta) | olvida todo: se puede llegar desde varios lados |
| Antes de `call` | guarda los valores sucios vivos después de la llamada |
| Después de `call` | olvida todo: el llamado usa los mismos registros |
| Último uso de un temporal | libera su registro sin guardarlo |

Todos los registros son *caller-saved*: el llamado no preserva nada, así que
el llamador guarda lo que necesita. Es más simple que repartir los `$s` y
sigue siendo correcto con recursividad, porque lo guardado va al marco de cada
activación.

---

## 5. Registros de activación (`marcos.py`)

Se respeta la disposición de `docs/DISENO_TAC.md` §5, con `$fp` apuntando a
la base del marco y desplazamientos positivos:

```
    $fp + 0          enlace de control (el $fp de quien llamó)
    $fp + 8          dirección de retorno ($ra)
    $fp + 16         parámetros (en orden de declaración)
                     variables locales
    $fp + base_t     temporales (8 bytes cada uno)
    $fp + this       receptor (solo métodos)
    ---------------- tamaño del marco (múltiplo de 8)
    $fp + S + ...    argumentos que apiló quien llamó
```

### Convención de llamada

```
    # llamador: param a / param b / t1 = call f, 2
    addiu $sp, $sp, -4
    sw    a, 0($sp)          # cada param apila una palabra
    addiu $sp, $sp, -4
    sw    b, 0($sp)
    jal   fn_f
    addiu $sp, $sp, 8        # desapila los argumentos
    move  rX, $v0            # resultado

fn_f:                        # prólogo
    addiu $sp, $sp, -S
    sw    $fp, 0($sp)        # enlace de control
    sw    $ra, 8($sp)        # dirección de retorno
    move  $fp, $sp
    lw    $a2, S+4($fp)      # argumento 0 (el primero apilado es el más profundo)
    sw    $a2, 16($fp)
    lw    $a2, S+0($fp)      # argumento 1
    sw    $a2, 20($fp)
    ...
fn_f_fin:                    # epílogo
    move  $sp, $fp
    lw    $ra, 8($sp)
    lw    $fp, 0($sp)
    addiu $sp, $sp, S
    jr    $ra
```

`return x` deja el valor en `$v0` y salta a `fn_f_fin`. En un método el
receptor es el primer argumento apilado y el prólogo lo copia a su celda.

**Recursividad.** Cada `jal` crea un marco nuevo bajo el anterior, con su
propia copia de parámetros, locales y temporales. El enlace de control
encadena los marcos: esa cadena es la rama actual del **árbol de activación**.

### Árbol de activación (`activacion.py`)

El árbol de activación depende de la ejecución, no del texto del programa. Para
mostrarlo, el backend incluye un **intérprete del TAC** que ejecuta el
programa y registra cada activación: función, argumentos, valor devuelto,
profundidad y tamaño del marco. El IDE lo dibuja y muestra la **salida
esperada**, que se compara con la de MARS.

---

## 6. Traducción por instrucción (`traductor.py`)

`TraductorMIPS` recorre cada unidad y despacha cada cuádruplo a un manejador.
Los manejadores de la parte 1:

| TAC | MIPS (enteros) |
|---|---|
| `x = y` | copia en descriptores; con conversión `cvt.s.w` si `x` es float e `y` entero |
| `x = y + z` / `-` | `addu` / `subu` (`addiu` con inmediato) |
| `x = y * z` | `mul` (con inmediato si `z` es literal) |
| `x = y / z` / `%` | `div y, z` + `mflo` / `mfhi` |
| `x = y < z`, `<=`, `>`, `>=`, `==`, `!=` | `slt`, `sle`, `sgt`, `sge`, `seq`, `sne` |
| `x = y && z` / `\|\|` | `and` / `or` (los booleanos son 0/1) |
| `x = !y` | `xori x, y, 1` |
| `x = -y` | `subu x, $zero, y` |
| float `+ - * /` | `mtc1` → `add.s`… → `mfc1` |
| float `< <= == …` | `c.lt.s` / `c.le.s` / `c.eq.s` + `movf`/`movt` |
| `print x` | syscall según el tipo (1, 2, 4 o `true`/`false`) + salto de línea |
| `param x` | apila una palabra |
| `x = call f, n` | `jal`, desapila `4·n`, `move x, $v0` |
| `return x` | `$v0 = x`, `j fn_f_fin` |

### Puntos de extensión (partes 2 y 3)

Las operaciones sin manejador se emiten como comentario
`# [pendiente] <cuádruplo>` y se listan como advertencia en el IDE. Cada parte
registra los suyos en `TraductorMIPS.manejadores`:

| Parte 2 (control y excepciones) | Parte 3 (datos compuestos) |
|---|---|
| `label`, `goto`, `if`, `ifFalse` | `newarray`, `=[]`, `[]=`, `length` |
| `antes_de_dividir` (división por cero → catch) | `new`, `=.`, `.=`, `obj+N` |
| `operando_especial` para variables capturadas | `concatenar` y comparación de cadenas |
| marcadores de `try` para el catch | `print` de arreglos/objetos |

El asignador ya maneja las fronteras de bloque en esas instrucciones: los
manejadores solo emiten el salto o la etiqueta.

---

## 7. Optimización por mirilla (`mirilla.py`)

Se aplica sobre el ensamblador ya generado, con una ventana deslizante, y se
repite hasta que ninguna regla cambie nada. El IDE muestra el código antes y
después y cuántas veces se aplicó cada regla.

| # | Transformación | Antes | Después |
|---|---|---|---|
| 1 | Movimiento redundante | `move $t0, $t0` | — |
| 2 | Carga tras almacenamiento | `sw $t0, 8($fp)` / `lw $t1, 8($fp)` | `sw …` / `move $t1, $t0` |
| 3 | Almacenamiento redundante | `lw $t0, 8($fp)` / `sw $t0, 8($fp)` | `lw …` |
| 4 | Salto a la siguiente instrucción | `j L1` / `L1:` | `L1:` |
| 5 | Cadena de saltos | `j L1` … `L1: j L2` | `j L2` |
| 6 | Código inalcanzable | `j L1` / `addu …` (sin etiqueta) | `j L1` |
| 7 | Identidades algebraicas | `addiu $t0, $t1, 0`, `mul $t0, $t1, 1` | `move $t0, $t1` |
| 8 | Reducción de fuerza | `mul $t0, $t1, 8` | `sll $t0, $t1, 3` |
| 9 | Fusión de ajustes de pila | `addiu $sp, $sp, -4` ×2 | `addiu $sp, $sp, -8` |
| 10 | Salto sobre salto | `beqz $t0, L1` / `j L2` / `L1:` | `bnez $t0, L2` / `L1:` |
| 11 | Etiquetas sin uso | `L7_if_fin:` sin referencias | — |

Solo se eliminan etiquetas internas (`L…`); las de funciones y `main` se
conservan. Ninguna regla cruza una etiqueta salvo la 4, la 5 y la 10, que
justamente razonan sobre ella.

---

## 8. Compuerta

La generación de ensamblador hereda la compuerta del TAC: si hubo cualquier
error léxico, sintáctico o semántico no hay TAC, y sin TAC no hay ensamblador.

---

## 9. Dónde está cada cosa

| Archivo | Contenido |
|---|---|
| `src/backend/programa_mips.py` | instrucciones MIPS, secciones `.data`/`.text`, literales |
| `src/backend/unidades.py` | separación del TAC en `main` y funciones; bloques básicos |
| `src/backend/vida.py` | análisis de vida de temporales y siguiente uso |
| `src/backend/registros.py` | descriptores de registro y dirección, `getReg` |
| `src/backend/marcos.py` | registros de activación MIPS, prólogo y epílogo |
| `src/backend/tipos.py` | tipo de cada operando del TAC |
| `src/backend/traductor.py` | `TraductorMIPS`: manejadores por cuádruplo |
| `src/backend/mirilla.py` | optimizador de mirilla |
| `src/backend/activacion.py` | intérprete del TAC y árbol de activación |
| `src/backend/backend.py` | punto de entrada `generar_ensamblador` |
