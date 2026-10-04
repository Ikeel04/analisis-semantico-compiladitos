# Diseño del lenguaje intermedio de Compiscript

Este documento define la representación intermedia que produce el compilador,
las decisiones que hay detrás y los supuestos que se tomaron al traducir. Es el
contrato que siguen los tres generadores (expresiones y control de flujo,
funciones, clases y arreglos).

---

## 1. Forma de las instrucciones: cuádruplos

El código intermedio es una lista de **cuádruplos**:

```
(operación, argumento1, argumento2, resultado)
```

Los cuatro campos existen siempre; los que una operación no usa quedan vacíos y
se muestran como `_`.

**Por qué cuádruplos y no triples.** En un triple el resultado de una
instrucción se referencia por su número de línea, así que mover o insertar una
instrucción obliga a renumerar todas las referencias. En un cuádruplo el
resultado tiene nombre propio, lo que permite reordenar sin reescribir nada y,
sobre todo, permite que cada temporal sea un símbolo al que la tabla de
símbolos le puede asignar una dirección. Como la siguiente fase es generación
de código objeto, necesitamos justamente eso.

Cada cuádruplo tiene además una forma impresa, cercana a la notación del
*Dragon Book*, que es la que se muestra en el IDE:

| Categoría | Cuádruplo | Se imprime |
|---|---|---|
| Asignación | `(=, a, _, x)` | `x = a` |
| Binaria | `(+, a, b, t1)` | `t1 = a + b` |
| Unaria (negativo) | `(-u, a, _, t1)` | `t1 = -a` |
| Unaria (negación) | `(!, a, _, t1)` | `t1 = !a` |
| Etiqueta | `(label, L1, _, _)` | `L1:` |
| Salto | `(goto, _, _, L1)` | `goto L1` |
| Salto si verdadero | `(if, t1, _, L1)` | `if t1 goto L1` |
| Salto si falso | `(ifFalse, t1, _, L1)` | `ifFalse t1 goto L1` |
| Inicio de función | `(function, f, _, _)` | `function f:` |
| Fin de función | `(endfunction, f, _, _)` | `endfunction f` |
| Paso de parámetro | `(param, x, _, _)` | `param x` |
| Llamada | `(call, f, 2, t1)` | `t1 = call f, 2` |
| Retorno | `(return, x, _, _)` | `return x` |
| Lectura indexada | `(=[], a, i, t1)` | `t1 = a[i]` |
| Escritura indexada | `([]=, i, x, a)` | `a[i] = x` |
| Instanciación | `(new, Perro, _, t1)` | `t1 = new Perro` |
| Lectura de campo | `(=., p, nombre, t1)` | `t1 = p.nombre` |
| Escritura de campo | `(.=, nombre, x, p)` | `p.nombre = x` |
| Impresión | `(print, a, _, _)` | `print a` |
| Longitud | `(length, a, _, t1)` | `t1 = length a` |
| Comentario | `(#, texto, _, _)` | `# texto` |

Las operaciones binarias usan como código el propio símbolo (`+`, `<`, `&&`,
…). Las unarias se distinguen con un sufijo (`-u`) para que el menos unario no
se confunda con la resta.

**Supuesto.** Un cuádruplo lee sus dos argumentos **antes** de escribir el
resultado. De ahí se deduce que `t1 = t1 * t2` es válido, que es la base del
reciclaje de temporales (sección 3).

### Convenciones de nombres

| | Forma | Se recicla |
|---|---|---|
| Temporales | `t1`, `t2`, … | sí |
| Etiquetas | `L1`, `L2`, … opcionalmente con pista: `L3_fin_while` | no |
| Funciones | nombre cualificado: `suma`, `Punto.constructor`, `contador.interno` | — |

Las etiquetas **no** se reciclan: una etiqueta es una posición del programa y
reutilizar el nombre haría que un salto aterrizara en otro lado. Los nombres de
función se cualifican con su clase o su función contenedora, de modo que dos
métodos `sumar` de clases distintas no colisionen.

**Operandos.** Un literal aparece tal cual (`42`, `2.5`, `"ana"`, `true`).
Una variable se referencia por su **dirección** (`global+N`, `fp+N`, `obj+N`),
la que `memoria.py` asigna a cada símbolo: el TAC es la entrada de la
generación de código objeto, que trabaja con desplazamientos y no con nombres
de fuente. Los temporales se referencian por su nombre (`tN`). Una instrucción
lee sus argumentos antes de escribir el resultado, así que `t1 = t1 + 1` es
válido y es la base del reciclaje.

---

## 2. Esquemas de traducción

Estos son los patrones que debe producir el generador. Se documentan aquí
porque son parte del diseño: fijan la forma del código antes de escribirlo.

### if / else

```
            <código de la condición, deja el valor en t>
            ifFalse t goto L1_else
            <código del bloque then>
            goto L2_fin
L1_else:
            <código del bloque else>
L2_fin:
```

Sin `else`, el `ifFalse` salta directo a `L2_fin` y desaparece el `goto`.

### while

```
L1_inicio:
            <código de la condición, deja el valor en t>
            ifFalse t goto L2_fin
            <código del cuerpo>
            goto L1_inicio
L2_fin:
```

`break` salta a `L2_fin` y `continue` a `L1_inicio`. El generador
mantiene una pila con esas dos etiquetas por cada ciclo abierto; como
el análisis semántico ya garantizó que `break` y `continue` solo
aparecen dentro de un ciclo, la pila nunca está vacía cuando se
consulta. En el `for` y el `foreach` el "continuar" es el paso
(`L_paso`), para no saltarse el incremento; en el `do-while`, la
etiqueta de la condición.

### do-while

Igual que el `while` pero con la condición al final, así que el cuerpo se
ejecuta al menos una vez y el salto de regreso es un `if` en vez de un `goto`.
La condición tiene su propia etiqueta (`L_cond`), que se emite al entrar
su expresión: es adónde salta `continue` (no al inicio, que re-ejecutaría
el cuerpo).

### for

Se traduce como un `while` con el inicializador antes de la etiqueta de inicio
y el paso de iteración justo antes del salto de regreso, de modo que `continue`
no se salte el incremento.

### foreach

Se **desarma** en un ciclo indexado sobre `length` (§1): el índice es un
temporal que vive todo el ciclo (por eso no se libera al comparar, y se
recicla en el incremento):

```
             t_i = 0
L1_inicio:
             t_len = length arr
             t_c = t_i < t_len
             ifFalse t_c goto L2_fin
             n = arr[t_i]
             <código del cuerpo>
L3_paso:
             t_i = t_i + 1
             goto L1_inicio
L2_fin:
```

`n` ya tiene dirección real (el análisis semántico la declara en el
ámbito del bloque). `break` salta a `L2_fin` y `continue` a `L3_paso`,
para no saltarse el incremento.

### switch

El sujeto se compara con cada caso en una **cadena** (sin fall-through:
cada caso salta al fin al terminar). El caso se evalúa **solo si los
anteriores no cuadraron** —evaluación perezosa, como una cadena de
`if/else`—, y el `default` es el destino natural del último "no cuadró":

```
             t = <sujeto>
             t1 = t == valor1
             ifFalse t1 goto L1_no
             <código del caso 1>
             goto L_fin
L1_no:
             t2 = t == valor2
             ifFalse t2 goto L2_no
             <código del caso 2>
             goto L_fin
L2_no:
             <código del default>
L_fin:
```

El sujeto vive en un temporal (o en su dirección) durante todo el
`switch` y se libera al cerrarlo; cada valor de caso se libera
después de su comparación.

### try / catch

```
             <código del try>
             goto L_fin
L_catch:
             <código del catch>
L_fin:
```

El `catch` **no** es alcanzado por el flujo normal: solo una excepción
de tiempo de ejecución (división por cero, índice fuera de rango, …)
aterriza en `L_catch`. Compiscript no tiene `throw`, así que el
generador solo deja dispuestos los bloques; quién salta a `L_catch`
lo decide la máquina.

### Ternario `? :`

```
             <código de la condición, deja el valor en t>
             ifFalse t goto L1_ternario_sino
             t_r = <rama verdadera>
             goto L2_ternario_fin
L1_ternario_sino:
             t_r = <rama falsa>
L2_ternario_fin:
```

Ambas ramas asignan al **mismo** temporal `t_r`, que es el valor de
la expresión: no importa cuál se ejecutó, `t_r` queda con el
resultado. El temporal del resultado se reserva antes de las dos
asignaciones (está vivo en toda la construcción) y la condición se
libera apenas se usa en el `ifFalse`.

### Llamada a función

```
            param a1
            param a2
            t1 = call f, 2
```

Los `param` van en el orden de declaración y el número del `call` es la
cantidad de argumentos, para que el generador de código objeto sepa cuántos
desapilar. Si la función es `void`, el `call` se emite sin resultado.

### Declaración de función

```
function f:
            <código del cuerpo>
            return t
endfunction f
```

---

## 3. Asignación y reciclaje de temporales

### El problema

Traducir una expresión obliga a guardar los resultados parciales. La traducción
ingenua crea un temporal nuevo cada vez:

```
(a + b) * (c + d) - (e + f)

t1 = a + b
t2 = c + d
t3 = t1 * t2
t4 = e + f
t5 = t3 - t4        ->  5 temporales
```

Cada temporal ocupa un espacio en el registro de activación de la función, así
que desperdiciarlos infla el marco de pila de **cada llamada**.

### El algoritmo

Un temporal solo está vivo entre que se escribe y que se consume. Apenas un
cuádruplo lo usa como argumento, su valor ya no hace falta y el nombre puede
volver a una bolsa de libres. La bolsa es una **pila (LIFO)**: reutilizar el
liberado más recientemente mantiene pequeño el conjunto de temporales vivos y
hace que la salida sea estable y legible.

El orden es la parte delicada: hay que **liberar los operandos antes de pedir el
temporal del resultado**. Es válido porque un cuádruplo lee antes de escribir.
Eso es exactamente lo que hace `temporal_para`:

```python
destino = pool.temporal_para(izquierda, derecha)
programa.emitir_binaria("+", izquierda, derecha, destino)
```

Se libera de derecha a izquierda, para que quede arriba de la pila el operando
*más a la izquierda* y el resultado reutilice su nombre. Así la salida queda
`t1 = t1 * t2` en vez de `t2 = t1 * t2`, que es la forma en que aparece en la
bibliografía y la más fácil de revisar a mano.

La misma expresión, con reciclaje:

```
t1 = a + b
t2 = c + d
t1 = t1 * t2
t2 = e + f
t1 = t1 - t2        ->  2 temporales (de 5)
```

### Reglas de seguridad

- Solo se recicla lo que el pool entregó. Una variable del programa que empieza
  con `t` (`total`, `t`, `t1a`) **no** es un temporal; reciclarla corrompería el
  programa.
- La doble liberación se ignora. Liberar dos veces dejaría el nombre repetido en
  la bolsa y dos valores distintos terminarían escribiendo en el mismo lugar.
- Cada función tiene su propio pool, apilado: al entrar a una función anidada se
  empuja uno nuevo y al salir se recupera el de quien la contiene, con sus
  temporales vivos intactos.

### Métrica

El **pico** de temporales vivos de un pool es exactamente cuántos *slots* hay
que reservar en el registro de activación de esa función. El pool también
reporta cuántos nombres creó, cuántas veces reutilizó y el ahorro, que es lo
que se muestra en el IDE.

---

## 4. Modelo de memoria

El análisis semántico deja una tabla de símbolos que sabe el nombre, la clase y
el tipo de cada identificador. Para generar código falta **dónde vive** cada
dato. Esa información la agrega `intermediate/memoria.py` recorriendo el árbol
de ámbitos ya terminado.

### Áreas

| Área | Qué guarda | Dirección |
|---|---|---|
| `global` | variables del ámbito global y de sus bloques sueltos | `global+N` |
| `parametro` | argumentos de una función | `fp+N` |
| `local` | variables de la función y de sus bloques | `fp+N` |
| `atributo` | campos de una clase, dentro del objeto | `obj+N` |

Las funciones y las clases no reciben dirección de dato: su «dirección» es una
etiqueta del código, no una celda de memoria.

### Tamaños

| Tipo | Bytes |
|---|---|
| `boolean` | 1 |
| `integer` | 4 |
| `float` | 8 |
| `string`, arreglos, objetos | 8 (referencia) |
| `void` | 0 |

**Supuesto:** máquina de 64 bits. Las cadenas, los arreglos y los objetos se
guardan por referencia: en el marco solo va el puntero, el contenido vive en el
heap. Un tipo que el análisis no pudo inferir se reserva como referencia, para
no desalinear el resto del marco.

### Alineación

Cada dato se alinea a su propio tamaño, con un máximo de una palabra (8 bytes).
Un `boolean` seguido de un `integer` deja 3 bytes de relleno, igual que haría un
compilador real:

```
let flag: boolean = true;    // global+0, 1 byte
let n: integer = 0;          // global+4, 4 bytes (saltó el relleno)
```

---

## 5. Registros de activación

Cada llamada reserva un marco con esta forma, direccionado desde el apuntador de
marco (`fp`):

```
    fp + 0     enlace de control (el fp de quien llamó)      8 bytes
    fp + 8     dirección de retorno                          8 bytes
    fp + 16    parámetros, en orden de declaración
               variables locales (incluidas las de sus bloques)
               temporales
    --------   tamaño total
```

**Recursividad.** Hay un registro de activación por función: es el *molde*. Cada
llamada instancia uno nuevo en la pila, con su propio `fp`. Por eso dos
activaciones de la misma función —el caso de `factorial(n-1)` llamándose a sí
misma— tienen cada una su copia de los parámetros, las locales y los temporales,
y no se pisan. El enlace de control es lo que permite volver al marco anterior
al terminar.

**Los temporales se reservan al final**, cuando ya se generó el TAC de la
función: antes de generar no se sabe cuántos hacen falta. El generador llama a
`fijar_temporales(pico)` al cerrar cada función.

### Ejemplo real

Para este programa:

```javascript
const MAX: integer = 100;

class Punto {
  var x: integer;
  var y: integer;
  function constructor(x: integer, y: integer) { this.x = x; this.y = y; }
}

class Punto3D : Punto { var z: integer; }

function suma(a: integer, b: integer): integer {
  var parcial: integer = a + b;
  return parcial;
}

let flag: boolean = true;
let n: integer = suma(2, 3);
```

el compilador produce:

```
área global: 12 bytes
instancia de 'Punto': 8 bytes
instancia de 'Punto3D': 12 bytes
registro de activación de 'Punto.constructor' (24 bytes)
  fp+0    enlace de control
  fp+8    dirección de retorno
  fp+16   x (parámetro · integer · 4b)
  fp+20   y (parámetro · integer · 4b)
registro de activación de 'suma' (28 bytes)
  fp+0    enlace de control
  fp+8    dirección de retorno
  fp+16   a (parámetro · integer · 4b)
  fp+20   b (parámetro · integer · 4b)
  fp+24   parcial (variable · integer · 4b)
```

Nótese que `Punto3D` mide 12 bytes y no 4: los atributos heredados van primero
(`x`, `y` en `obj+0` y `obj+4`), y `z` queda en `obj+8`. Eso es deliberado: así
una instancia de la subclase se puede tratar como una de la clase base sin
recalcular desplazamientos.

---

## 6. La compuerta: cuándo se genera

El enunciado lo exige de forma explícita:

> Si se encuentra algún error, ya sea léxico, sintáctico o semántico, no deberá
> generarse representación intermedia.

El pipeline tiene dos compuertas, por razones distintas:

1. El **análisis semántico** corre solo si el sintáctico no falló: con un árbol
   incompleto no tiene sentido reportar errores de tipos sobre nodos mal
   formados.
2. La **generación de código intermedio** corre solo si no hubo **ningún** error
   de ningún tipo. Es más estricta: basta un solo error semántico, con el árbol
   perfectamente formado, para no generar nada.

Las direcciones de memoria sí se calculan aunque haya errores. No son código
intermedio: son información de la tabla de símbolos, y sirven para revisarla en
el IDE aunque el programa todavía no compile.

---

## 7. Supuestos y simplificaciones conocidas

- **Bloques hermanos no comparten espacio.** Las variables de todos los bloques
  de una función se acumulan en el mismo marco. Reutilizar el espacio entre
  bloques que nunca están vivos a la vez es una optimización posible; se
  prefirió la versión conservadora para que la dirección de cada símbolo sea
  única y fácil de verificar a mano.
- **Los temporales se reservan como palabra completa** (8 bytes), sin mirar el
  tipo del resultado intermedio. Simplifica el cálculo del marco a cambio de
  algo de espacio.
- **No hay optimización de mirilla** ni eliminación de saltos redundantes: el
  TAC se emite tal como sale de la traducción. El alcance del proyecto llega
  hasta la representación intermedia.
- **El enlace de acceso (static link) no se modela.** Compiscript permite
  funciones anidadas que leen variables del entorno donde se definieron; el
  análisis semántico ya registra esas capturas en
  `symbol.extra["captured"]`, pero el marco solo guarda el enlace de control.
  Resolver el acceso a una variable capturada en tiempo de ejecución queda para
  la fase de generación de código objeto.

---

## 8. Dónde está cada cosa

| Archivo | Contenido |
|---|---|
| `src/intermediate/tac.py` | cuádruplos, catálogo de operaciones, `ProgramaTAC` |
| `src/intermediate/temporales.py` | `PoolTemporales` (reciclaje), `GeneradorEtiquetas` |
| `src/intermediate/memoria.py` | tamaños, alineación, direcciones, registros de activación |
| `src/intermediate/generador.py` | `GeneradorTAC`: infraestructura compartida y punto de entrada |
| `src/intermediate/listener_tac.py` | `ListenerTAC`: recorre el árbol y traduce a cuádruplos |
| `src/semantic/symbol_table.py` | campos `area`, `offset`, `tamano`, `direccion` y `Scope.registro` |
| `src/compiler/pipeline.py` | la compuerta |

Tests: `tests/test_tac.py`, `tests/test_temporales.py`, `tests/test_memoria.py`,
`tests/test_generacion.py`.
