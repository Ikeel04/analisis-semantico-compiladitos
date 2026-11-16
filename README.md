# Compiscript — Compilador hasta ensamblador MIPS

Compilador de Compiscript: análisis léxico, sintáctico y semántico, generación
de código intermedio (TAC, cuádruplos) y generación de ensamblador **MIPS32** a
partir de ese TAC, con interfaz gráfica en Streamlit. El `.asm` se ejecuta en
**MARS 4.5**. Si el programa tiene cualquier error, no se genera código
intermedio ni ensamblador.

## Qué incluye

- **Analizador léxico** (`src/lexico/`): reconoce tokens y reporta errores de
  tipo léxico (caracteres o números mal formados).
- **Analizador sintáctico** (`src/parser/`): parser ANTLR a partir de una
  gramática; construye el árbol sintáctico (LISP y estructura para dibujarlo).
- **Analizador semántico** (`src/semantic/`):
  - **Tabla de símbolos y ámbitos** (`symbol_table.py`): scopes global, de
    función, de clase y de bloque; `insert` / `lookup` / `update`.
  - **Sistema de tipos** (`type_system.py`): `integer`, `string`, `boolean`,
    `null`, `void`, arreglos `T[]` y clases.
  - **Generador de la tabla de símbolos** (`listener.py`): traduce el árbol
    ANTLR a llamadas del checker.
  - **Reglas semánticas** (`checker.py`): variables no declaradas /
    redeclaradas, control de flujo (`break`/`continue`), `return`,
    declaración `var`/`const`/`function`, condiciones y ciclos, `switch`,
    `try/catch`, `print`, clases y objetos (herencia, `new`, `this`, métodos y
    atributos) e índices de arreglos.
  - **Reglas generales** (`checker.py` + `listener.py`): código inalcanzable
    (tras `return`/`break`/`continue`), `case` duplicado en `switch`,
    expresiones sin sentido (autocomparación, división/módulo por `0`,
    condición constante, `print` de `void`).
- **Generación de código intermedio** (`src/intermediate/`):
  - **Diseño del TAC** (`tac.py`): cuádruplos `(op, arg1, arg2, resultado)` y el
    catálogo de instrucciones del lenguaje intermedio.
  - **Temporales y etiquetas** (`temporales.py`): algoritmo de asignación y
    **reciclaje** de temporales, y generador de etiquetas únicas.
  - **Memoria** (`memoria.py`): direcciones por símbolo, tamaños, alineación y
    **registros de activación** por función.
  - **Traducción del árbol** (`listener_tac.py`): recorre el árbol y emite los
    cuádruplos de variables y constantes, expresiones aritméticas y lógicas,
    arreglos (`newarray`, índices, matrices), control de flujo (`if`, `while`,
    `do-while`, `for`, `foreach`, `switch`, `break`/`continue`), funciones,
    recursividad, `try/catch`, clases, objetos (`new`, `this`, atributos,
    métodos) y herencia.
  - **Infraestructura del generador** (`generador.py`): el estado compartido que
    usan los generadores de expresiones, control de flujo, funciones y clases.
- **Generación de código ensamblador MIPS32** (`src/backend/`), a partir del
  TAC:
  - **Selección de registros** (`registros.py`, `vida.py`): algoritmo getReg con
    descriptores de registro y de dirección, bloques básicos y análisis de vida.
  - **Registros de activación** (`marcos.py`): marco en la pila con enlace de
    control, dirección de retorno, parámetros, locales, temporales y receptor;
    prólogo, epílogo y convención de llamada.
  - **Control de flujo y try/catch** (`control.py`): saltos y etiquetas
    (`label`/`goto`/`if`/`ifFalse`, `break`/`continue`) y try/catch (pila
    `__pila_try`, rutinas `__error_*` y `__lanzar`).
  - **Arreglos, clases, herencia y cadenas** (`datos.py`): arreglos en el heap
    con verificación de null y de límites, matrices, `length`; objetos con
    `new`, atributos por offset (heredados primero), atributos sin `this`
    dentro de métodos; concatenación y comparación de cadenas e impresión de
    arreglos con rutinas de soporte.
  - **Traducción** (`traductor.py`, `tipos.py`): variables y constantes,
    expresiones aritméticas (enteros y float), lógicas y relacionales, `print`,
    llamadas y retornos.
  - **Optimización por mirilla** (`mirilla.py`): 11 transformaciones.
  - **Árbol de activación** (`activacion.py`): intérprete del TAC que registra
    cada llamada y produce la salida esperada.
  - **Extensiones** (`extensiones.py`): donde se enchufan control de flujo,
    try/catch, arreglos, clases y cadenas.
- **Pipeline unificado** (`src/compiler/pipeline.py`): junta los errores de los
  tres analizadores ordenados por línea y columna, expone los ámbitos finales y
  **genera el código intermedio solo si no hubo ningún error**.
- **IDE** (`app.py`): editor, tabla unificada de errores con métricas y filtro,
  tabla de tokens, pestaña de ámbitos (tabla de símbolos), árbol sintáctico,
  **código intermedio** (instrucciones o cuádruplos, métricas de reciclaje de
  temporales y descarga del `.tac`) y **memoria** (direcciones y registros de
  activación). Las dos últimas avisan cuando no se generó código por haber
  errores. Además: **ensamblador** (optimizado, sin optimizar o comparados,
  reglas de mirilla aplicadas y descarga del `.asm`), **registros** (traza
  cuádruplo → MIPS con el descriptor de registros) y **activación** (árbol de
  activación, salida esperada y marcos MIPS).

## Documentación

- [`docs/DISENO_TAC.md`](docs/DISENO_TAC.md) — diseño del lenguaje intermedio:
  juego de instrucciones, esquemas de traducción, algoritmo de reciclaje de
  temporales, modelo de memoria, registros de activación y supuestos.
- [`docs/DISENO_MIPS.md`](docs/DISENO_MIPS.md) — diseño del backend MIPS:
  organización del programa, selección de registros, marcos en la pila,
  traducción por instrucción, mirilla, extensiones y estado por parte.

## Uso

Requiere Python 3.11 o similar. Con el entorno virtual activado:

```bash
# Dependencias (ANTLR runtime, Streamlit y matplotlib)
python -m pip install -r requirements.txt

# Batería de tests
python -m unittest discover -s tests -v

# Interfaz gráfica
python -m streamlit run app.py
```

### Ejecutar el ensamblador en MARS

El `.asm` que se descarga del IDE se ensambla y ejecuta en MARS 4.5
(<https://github.com/dpetersanderson/MARS/releases>, requiere Java 8 o más).

Desde consola:

```bash
java -jar Mars4_5.jar nc programa.asm
```

Con la interfaz de MARS: `File → Open` el `.asm`, `Run → Assemble` (F3) y
`Run → Go` (F5); la salida aparece en «Run I/O». La salida debe ser igual a la
**salida esperada** que muestra la pestaña «Activación» del IDE (la produce el
intérprete del TAC).

Los tests que comparan la salida de MARS con la esperada corren si la variable
`MARS_JAR` apunta al `.jar` (si no, se saltan):

```bash
export MARS_JAR=/ruta/Mars4_5.jar      # PowerShell: $env:MARS_JAR = "C:\ruta\Mars4_5.jar"
python -m unittest discover -s tests -v
```

En el IDE: elegir un `.cps` (o un ejemplo) en la barra lateral, pulsar
«Compilar» y revisar las pestañas. El código intermedio aparece en «Código
intermedio» solo si no hubo ningún error léxico, sintáctico ni semántico.

Tests del código intermedio: `test_tac` (instrucciones), `test_temporales`
(reciclaje), `test_memoria` (direcciones), `test_generacion` (compuerta),
`test_tac_expresiones`, `test_tac_controlflujo`, `test_tac_funciones`,
`test_tac_arreglos` y `test_tac_clases`.

Tests del backend MIPS: `test_mips_registros` (descriptores, getReg, vida y
bloques), `test_mips_traductor` (marcos, llamadas, expresiones, compuerta y
ejecución en MARS), `test_mips_control` (saltos y etiquetas, try/catch),
`test_mips_mirilla` (cada regla y equivalencia en MARS),
`test_mips_activacion` (árbol, salida y límites), `test_mips_datos` (arreglos,
objetos, herencia y cadenas: casos exitosos y fallidos en MARS) y
`test_mips_ejemplos` (todo `ejemplos/asm_*.cps` en MARS contra la salida
esperada, optimizado y sin optimizar).

## Sistemas de tipos y ámbito (matriz de conformidad)

| Requisito | Implementación | Tests (éxito/fallo) |
| --- | --- | --- |
| Aritmética `+ - * / %`: operandos `integer`/`float` | `type_system.arithmetic` (numerics; `+` concatena strings) | `test_type_system.TestOperacionesAritmeticas` |
| Lógicas `&& \|\| !`: operandos `boolean` | `type_system.logical` / `unary` | `test_type_system.TestOperacionesLogicas` |
| Comparaciones `== != < <= > >=`: mismo tipo compatible | `type_system.comparison` (`comparable`, relacionales numéricas) | `test_type_system.TestComparaciones` |
| Asignaciones: tipo del valor == tipo declarado | `checker.check_compatible` | `test_checker` (éxito y fallo) |
| `const` inicializada en su declaración | gramática obliga `=`; `declare_constant` | `test_checker.TestConstantes` |
| Listas/estructuras | `array_literal`, `check_index`, `check_index_assign` | `test_checker`, `test_classes`, `test_listener` |
| Resolución local/global | `SymbolTable.lookup` sobre la cadena de ámbitos | `test_symbol_table` |
| Variable no declarada | `use_variable`/`check_assignment` | `test_listener.test_variable_no_declarada` |
| Redeclaración en el mismo ámbito | `Scope.declare_here` + `declare_function` (sin sobrecarga) | `test_symbol_table`, `test_classes` |
| Entorno por función/clase/bloque | `enter_scope("function"/"class"/"block")` | `test_symbol_table.TestAmbitos` |
| Argumentos en llamadas (posicionales) | `check_call` | `test_checker`, `test_listener` (número y tipo) |
| Tipo de retorno de función | `check_return` | `test_checker.TestFunciones` |
| Recursión | declaración previa al cuerpo + `check_call` | `test_checker`, `test_listener.TestFunciones` |
| Funciones anidadas / closures | ámbito anidado + `use_variable` registra `captured` | `test_checker`, `test_listener.TestFunciones` |
| Múltiples declaraciones de función | `_insert` detecta redeclaración | `test_checker` |
| Condiciones `boolean` en if/while/do-while/for | `check_condition` | `test_checker.TestCondiciones`, `test_listener` |
| `break`/`continue` solo en bucles | `enter_loop`/`exit_loop`/`in_loop` | `test_checker.TestControlDeFlujo` |
| `return` solo dentro de una función | `check_return` (pila de frames) | `test_checker`, `test_listener.TestFunciones` |
| Atributos/métodos con `.` | `check_member_access`, `check_member_call`, `_resolver_miembro` | `test_classes` |
| Constructor correcto (`new`) | `check_new` + `_buscar_constructor` | `test_classes.TestConstructores` |
| `this` en métodos | `_classes` + `check_this` | `test_classes.TestThis` |
| Tipo de elementos en listas | `array_literal` (`unify`) | `test_type_system`, `test_classes` |
| Índices válidos de listas | `check_index` (tipo `integer`, arreglo) | `test_classes.TestIndices`, `test_listener` |
| Código muerto (tras return/break/continue) | secuencias de sentencias en el listener | `test_listener.TestReglasGenerales` |
| Expresiones con sentido (no multiplicar funciones) | `use_variable` rechaza función/clase como valor | `test_checker`, `test_listener.TestFunciones` |
| Declaraciones duplicadas (variables y parámetros) | `Scope.declare_here` | `test_symbol_table`, `test_checker` |

### Decisiones de diseño
- **Tipos numéricos**: `integer` y `float` (la gramática genera literales de ambos;
  `integer → float` es asignación válida por widening, a la inversa no).
- **`switch`**: evalúa el sujeto y lo compara con cada `case` (no exige `boolean`,
  como acostumbran C/Java); las condiciones de `if`/`while`/`do-while`/`for`
  **sí** deben ser `boolean`.

## Ejemplos

En `ejemplos/` hay programas válidos (`ok_*.cps`), con errores léxicos,
sintácticos, semánticos y mixtos (`errores_*.cps`), y uno por cada ítem de la
generación de código intermedio (`tac_*.cps`):

| Archivo | Qué muestra |
| --- | --- |
| `tac_01_variables.cps` | declaración y asignación de variables y constantes |
| `tac_02_aritmeticas.cps` | precedencia, paréntesis, unario y reciclaje de temporales |
| `tac_03_logicas.cps` | `&&`, `\|\|`, `!` y comparaciones |
| `tac_04_control.cps` | `if/else`, `while`, `do-while`, `for`, `foreach`, `switch`, `break`, `continue` |
| `tac_05_funciones.cps` | funciones, parámetros, retorno, `void` y función anidada |
| `tac_06_recursividad.cps` | factorial y fibonacci |
| `tac_07_trycatch.cps` | `try/catch` |
| `ok_arreglos.cps` | arreglos: literal, índices, matrices |
| `ok_clases.cps` | clases, objetos, atributos, métodos |
| `tac_08_herencia.cps` | herencia de 3 niveles, métodos redefinidos, constructor heredado |
| `asm_01_variables.cps` | ensamblador: variables y constantes (byte, palabra, float) |
| `asm_02_expresiones.cps` | ensamblador: aritméticas, lógicas, float, reducción de fuerza |
| `asm_03_registros.cps` | ensamblador: presión de registros y desalojos de getReg |
| `asm_04_activacion.cps` | ensamblador: marcos, parámetros de varios tipos, llamadas anidadas |
| `asm_05_control.cps` | ensamblador: control de flujo (`if`, `while`, `for`, `switch`, `break`, `continue`, `do-while`) |
| `asm_06_funciones.cps` | ensamblador: funciones anidadas con variables capturadas (enlace de acceso) |
| `asm_07_recursividad.cps` | ensamblador: recursividad con control de flujo (caso base) |
| `asm_08_trycatch.cps` | ensamblador: `try/catch` (error capturado, división por cero) |
| `asm_09_arreglos.cps` | ensamblador: arreglos en el heap, límites, matrices, `foreach`, arreglos como parámetro, índice fuera de rango atrapado |
| `asm_10_clases.cps` | ensamblador: `new`, atributos (`boolean` de 1 byte), métodos con atributos sin `this`, objetos como parámetros y en arreglos |
| `asm_11_herencia.cps` | ensamblador: 3 niveles, atributos heredados e inicializados en la declaración, métodos redefinidos, constructor heredado |
| `asm_12_cadenas.cps` | ensamblador: concatenación en tiempo de ejecución, recursión con cadenas, `==`/`!=` por contenido |

Todos los `asm_*.cps` se verifican solos con `tests/test_mips_ejemplos.py`: no
dejan instrucciones pendientes y MARS imprime lo mismo que el intérprete.

### Rúbrica del Proyecto 3 y dónde está cada punto

| Ítem | Dónde | Ejemplo |
| --- | --- | --- |
| Selección de registros (4) | `registros.py`, `vida.py`, pestaña «Registros» | `asm_03_registros.cps` |
| Registros y árbol de activación (5) | `marcos.py`, `activacion.py`, pestaña «Activación» | `asm_04_activacion.cps` |
| Variables y constantes (1) | `traductor.py` | `asm_01_variables.cps` |
| Expresiones aritméticas (1) | `traductor.py` | `asm_02_expresiones.cps` |
| Expresiones lógicas (1) | `traductor.py` | `asm_02_expresiones.cps` |
| Arreglos (1) | `datos.py` | `asm_09_arreglos.cps` |
| Sentencias de control (3) | `control.py` | `asm_05_control.cps` |
| Funciones y parámetros (2) | `traductor.py`, `marcos.py` | `asm_06_funciones.cps` |
| Recursividad (2) | `marcos.py`, `control.py` | `asm_07_recursividad.cps` |
| Clases y objetos (2) | `datos.py` | `asm_10_clases.cps` |
| Herencia (2) | `datos.py` + TAC | `asm_11_herencia.cps` |
| try/catch (2) | `control.py` | `asm_08_trycatch.cps`, `asm_09_arreglos.cps` |
| Mirilla, al menos 6 (3) | `mirilla.py` (11 reglas), tabla en «Ensamblador» | cualquiera |
| Simulador compatible (1) | MARS 4.5, `tests/test_mips_*.py` | — |

### Limitaciones conocidas

- Enlace estático de métodos (sin tabla virtual): el método que se llama es el
  del tipo declarado de la variable (`DISENO_TAC.md` §7).
- `print` de un objeto imprime su dirección (el intérprete muestra `<Clase>`):
  en los ejemplos se imprimen sus atributos. Los arreglos de `integer`,
  `boolean` y `string` (de cualquier dimensión) sí se imprimen como `[1, 2]`.
- `float` dentro de una concatenación no se convierte a cadena (el formato de
  Java no es fácil de igualar); Compiscript tampoco permite `string + float`.
