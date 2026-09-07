# Compiscript — Análisis semántico

Analizador completo (léxico + sintáctico + semántico) del lenguaje Compiscript,
con interfaz gráfica en Streamlit.

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
- **Pipeline unificado** (`src/compiler/pipeline.py`): junta los errores de los
  tres analizadores ordenados por línea y columna y expone los ámbitos finales.
- **IDE** (`app.py`): editor, tabla unificada de errores con métricas y filtro,
  tabla de tokens, pestaña de ámbitos (tabla de símbolos) y árbol sintáctico.

## Uso

```bash
# Análisis por consola (tests)
python3 -m unittest discover -s tests -v

# Interfaz gráfica
streamlit run app.py
```

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

En `ejemplos/` hay programas válidos (`ok_*.cps`) y con errores léxicos,
sintácticos o mixtos (`errores_*.cps`).