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

## Persona

**Persona 3** — Clases/Objetos + Listas + Generales + IDE. Pasos:

1. Infraestructura (parser + pipeline + IDE).
2. Listener semántico + clases y objetos + integración de pipeline.
3. Reglas generales (código muerto, `case` duplicado, expresiones sin sentido,
   `print` de void).
4. IDE completo + tabla de ámbitos + README.

## Ejemplos

En `ejemplos/` hay programas válidos (`ok_*.cps`) y con errores léxicos,
sintácticos o mixtos (`errores_*.cps`).