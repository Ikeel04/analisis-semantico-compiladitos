"""Interfaz gráfica de Compiscript con Streamlit.

Permite seleccionar un archivo .cps, escribir código directamente o cargar un
ejemplo, y ejecutar el análisis con el botón «Compilar». Los tres analizadores
(léxico, sintáctico y semántico) corren juntos: sus errores se muestran en una
tabla unificada y el árbol sintáctico y los ámbitos (tabla de símbolos) también
tienen su pestaña en la interfaz.

Uso:
    streamlit run app.py
"""

import html
import os
import sys
from pathlib import Path

# Módulos flat de src/: se agregan las carpetas al path como en los tests.
_BASE = Path(__file__).resolve().parent
for _carpeta in ("src/parser", "src/lexico", "src/compiler", "src/ide", "src/semantic"):
    _ruta = str(_BASE / _carpeta)
    if _ruta not in sys.path:
        sys.path.insert(0, _ruta)

import streamlit as st

from arbol import figura_arbol
from pipeline import MENSAJE_EXITO, FilaError, ResultadoAnalisis, analizar_codigo
from analizador import Token
from symbol_table import SymbolTable, SemanticError

CARPETA_EJEMPLOS = _BASE / "ejemplos"

st.set_page_config(page_title="Compiscript — Analizador", page_icon="🔤", layout="wide")


def _inyectar_css() -> None:
    """Estilo de editor de código (tema oscuro tipo VSCode)."""
    st.markdown(
        """
        <style>
        [data-testid="stTextArea"] {
            border-radius: 6px;
            overflow: hidden;
        }
        [data-testid="stTextArea"] textarea {
            background-color: #1E1E1E;
            color: #D4D4D4;
            font-family: "SF Mono", Menlo, Consolas, "Liberation Mono", monospace;
            font-size: 14px;
            line-height: 1.6;
            border: 1px solid #3C3C3C;
            border-radius: 6px;
            caret-color: #569CD6;
        }
        [data-testid="stTextArea"] textarea:focus {
            border-color: #569CD6;
            box-shadow: 0 0 0 1px #569CD6;
        }
        [data-testid="stTabs"] button p {
            font-weight: 600;
        }
        [data-testid="stTabs"] button[aria-selected="true"] p {
            color: #569CD6;
        }
        .barra-archivo {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 4px 0 12px 0;
        }
        .chip-archivo {
            font-family: "SF Mono", Menlo, Consolas, monospace;
            font-size: 13px;
            color: #E6E6E6;
            background-color: #2D2D2D;
            border: 1px solid #3C3C3C;
            border-radius: 4px;
            padding: 3px 10px;
        }
        .chip-estado {
            font-size: 12px;
            font-weight: 600;
            border-radius: 12px;
            padding: 3px 12px;
        }
        .chip-estado.sin-analizar { background-color: #3C3C3C; color: #CCCCCC; }
        .chip-estado.valido      { background-color: #2A5A2A; color: #8FE388; }
        .chip-estado.con-errores { background-color: #5A2A2A; color: #FF9E9E; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _tabla_de_tokens(tokens: list[Token]):
    """Tabla de tokens reconocidos en el formato que se muestra en la interfaz."""
    return [
        {"Línea": t.linea, "Columna": t.columna, "Tipo": t.tipo, "Lexema": t.lexema}
        for t in tokens
    ]


def _tabla_de_errores(errores: list[FilaError]):
    """Tabla de errores con el formato común exigido por la especificación."""
    return [
        {
            "Tipo": e.tipo,
            "Línea": e.linea,
            "Columna": e.columna,
            "Símbolo / Lexema": e.simbolo,
            "Descripción": e.descripcion,
        }
        for e in errores
    ]


def _demo_tabla_simbolos() -> list[dict]:
    """Recrea en vivo insertar/recuperar/actualizar/manejo de ámbitos sobre
    una SymbolTable nueva, para la pestaña de demo. Cada paso trae el
    fragmento de código ejecutado y el resultado obtenido."""
    st_demo = SymbolTable()
    pasos = []

    def paso(seccion, codigo, resultado):
        pasos.append({"seccion": seccion, "codigo": codigo, "resultado": resultado})

    # 1) Insertar
    sym = st_demo.insert("edad", "variable", type_="integer")
    paso("Insertar", "insert('edad', 'variable', type_='integer')", f"OK -> {sym}")
    try:
        st_demo.insert("edad", "variable", type_="string")
        paso("Insertar", "insert('edad', ...) otra vez, mismo ámbito", "no debería llegar aquí")
    except SemanticError as e:
        paso("Insertar", "insert('edad', ...) otra vez, mismo ámbito", f"Error esperado -> {e}")

    # 2) Recuperar
    paso("Recuperar", "lookup('edad')", str(st_demo.lookup("edad")))
    paso("Recuperar", "lookup('no_existe')", str(st_demo.lookup("no_existe")))

    # 3) Actualizar
    tipo_antes = st_demo.lookup("edad").type
    st_demo.update("edad", type_="float")
    tipo_despues = st_demo.lookup("edad").type
    paso("Actualizar", "update('edad', type_='float')", f"{tipo_antes} -> {tipo_despues}")
    try:
        st_demo.update("fantasma", type_="integer")
        paso("Actualizar", "update('fantasma', ...)", "no debería llegar aquí")
    except SemanticError as e:
        paso("Actualizar", "update('fantasma', ...)", f"Error esperado -> {e}")

    # 4) Manejo de ámbitos
    st_demo.insert("global_var", "variable", type_="integer")
    st_demo.enter_scope("function", name="calcular")
    st_demo.insert("local_var", "variable", type_="integer")
    paso(
        "Manejo de ámbitos",
        "enter_scope('function', 'calcular'); insert('local_var', ...)",
        f"global_var visible: {st_demo.lookup('global_var')} | local_var: {st_demo.lookup('local_var')}",
    )
    st_demo.enter_scope("block", name="if-interno")
    st_demo.insert("local_var", "variable", type_="string")
    paso(
        "Manejo de ámbitos",
        "enter_scope('block'); insert('local_var', type_='string') (sombra)",
        f"local_var dentro del bloque: {st_demo.lookup('local_var')}",
    )
    st_demo.exit_scope()
    paso("Manejo de ámbitos", "exit_scope()  # sale del bloque", f"local_var: {st_demo.lookup('local_var')}")
    st_demo.exit_scope()
    paso("Manejo de ámbitos", "exit_scope()  # sale de la función", f"local_var: {st_demo.lookup('local_var')}")
    paso("Árbol de ámbitos final", "describe_tree()", st_demo.describe_tree())

    return pasos


def _estado_badge(resultado: ResultadoAnalisis | None, codigo: str) -> tuple[str, str]:
    """Devuelve (clase css, texto) del estado actual del archivo."""
    if resultado is None:
        return "sin-analizar", "Sin analizar"
    if codigo != st.session_state.get("analizado"):
        return "sin-analizar", "Sin analizar (cambios)"
    if resultado.es_valido:
        return "valido", "Válido"
    return "con-errores", f"Con errores ({len(resultado.errores)})"


def _mostrar_barra_estado(nombre: str, resultado: ResultadoAnalisis | None, codigo: str) -> None:
    clase, texto = _estado_badge(resultado, codigo)
    st.markdown(
        f'<div class="barra-archivo">'
        f'<span class="chip-archivo">{html.escape(nombre)}</span>'
        f'<span class="chip-estado {clase}">{texto}</span>'
        f"</div>",
        unsafe_allow_html=True,
    )


_inyectar_css()

# Estado de la sesión: el código nunca se pierde al cambiar de pestaña.
st.session_state.setdefault("codigo", "")
st.session_state.setdefault("nombre", "Nuevo archivo")
st.session_state.setdefault("resultado", None)
st.session_state.setdefault("analizado", None)


with st.sidebar:
    st.header("Compiscript")
    st.caption("Analizador léxico, sintáctico y semántico")

    subido = st.file_uploader("Abrir archivo .cps", type=["cps"])
    if subido is not None:
        try:
            contenido = subido.getvalue().decode("utf-8")
        except UnicodeDecodeError:
            st.error("El archivo no se pudo leer como texto UTF-8.")
        else:
            st.session_state["codigo"] = contenido
            st.session_state["nombre"] = subido.name
            st.session_state["resultado"] = None
            st.session_state["analizado"] = None

    ejemplos = sorted(p.name for p in CARPETA_EJEMPLOS.glob("*.cps"))
    ejemplo = st.selectbox(
        "Cargar ejemplo",
        ejemplos,
        index=None,
        placeholder="Elige un archivo de ejemplo…",
    )
    if st.button("Cargar ejemplo", width="stretch") and ejemplo:
        contenido = (CARPETA_EJEMPLOS / ejemplo).read_text(encoding="utf-8")
        st.session_state["codigo"] = contenido
        st.session_state["nombre"] = ejemplo
        st.session_state["resultado"] = None
        st.session_state["analizado"] = None

    st.divider()

    if st.button("Compilar", type="primary", width="stretch"):
        codigo = st.session_state["codigo"]
        if not codigo.strip():
            st.warning("Escribe algún código Compiscript o carga un archivo .cps.")
        else:
            st.session_state["resultado"] = analizar_codigo(st.session_state["nombre"], codigo)
            st.session_state["analizado"] = codigo

    if st.button("Limpiar", width="stretch"):
        st.session_state["codigo"] = ""
        st.session_state["nombre"] = "Nuevo archivo"
        st.session_state["resultado"] = None
        st.session_state["analizado"] = None


codigo = st.session_state["codigo"]
nombre = st.session_state["nombre"]
resultado = st.session_state["resultado"]

_mostrar_barra_estado(nombre, resultado, codigo)

tab_editor, tab_errores, tab_tokens, tab_ambitos, tab_arbol, tab_demo_ts = st.tabs(
    ["Editor", "Errores", "Tokens", "Ámbitos", "Árbol", "Demo tabla de símbolos"]
)

with tab_editor:
    st.text_area(
        "Código Compiscript",
        key="codigo",
        height=430,
        label_visibility="collapsed",
        placeholder='Ej.: let saludo: string = "hola";\nprint(saludo);',
    )

with tab_errores:
    if resultado is None:
        st.info("Pulsa «Compilar» en la barra lateral para revisar el código.")
    elif resultado.es_valido:
        st.success(MENSAJE_EXITO)
    else:
        st.error(
            f"Se encontraron {len(resultado.errores)} error(es) "
            "léxico(s), sintáctico(s) o semántico(s)."
        )

        col_total, col_lex, col_sin, col_sem = st.columns(4)
        col_total.metric("Total", len(resultado.errores))
        col_lex.metric("Léxicos", sum(1 for e in resultado.errores if e.tipo == "Léxico"))
        col_sin.metric("Sintácticos", sum(1 for e in resultado.errores if e.tipo == "Sintáctico"))
        col_sem.metric("Semánticos", sum(1 for e in resultado.errores if e.tipo == "Semántico"))

        tipo = st.radio(
            "Filtrar por tipo",
            ["Todos", "Léxico", "Sintáctico", "Semántico"],
            horizontal=True,
            label_visibility="collapsed",
        )
        filas = _tabla_de_errores(resultado.errores)
        if tipo != "Todos":
            filas = [fila for fila in filas if fila["Tipo"] == tipo]
        st.dataframe(filas, width="stretch", hide_index=True)

with tab_tokens:
    if resultado is None:
        st.info("Pulsa «Compilar» para generar la tabla de tokens.")
    elif resultado.tokens:
        st.dataframe(
            _tabla_de_tokens(resultado.tokens),
            width="stretch",
            hide_index=True,
        )
    else:
        st.write("No se reconoció ningún token.")

with tab_ambitos:
    if resultado is None:
        st.info("Pulsa «Compilar» para revisar los ámbitos y la tabla de símbolos.")
    elif resultado.ambitos:
        st.caption(
            "Árbol de ámbitos del análisis semántico: global, funciones, clases y bloques. "
            "Cada ámbito muestra sus símbolos con tipo."
        )
        st.dataframe(resultado.ambitos, width="stretch", hide_index=True)
        with st.expander("Ver los ámbitos como texto"):
            st.code(resultado.ambitos_texto, language="text")
    else:
        st.write("El análisis semántico no produjo ámbitos (¿el código tiene errores?).")

with tab_arbol:
    if resultado is None:
        st.info("Pulsa «Compilar» para construir el árbol sintáctico.")
    elif resultado.arbol_estructura:
        st.pyplot(figura_arbol(resultado.arbol_estructura), width="stretch")
        with st.expander("Ver el árbol como texto"):
            st.code(resultado.arbol, language="text")
    else:
        st.write("No se pudo construir el árbol sintáctico.")

with tab_demo_ts:
    st.caption(
        "Demo aislada de la tabla de símbolos (independiente del código del editor): "
        "insertar, recuperar, actualizar y manejo de ámbitos, paso a paso."
    )
    pasos = _demo_tabla_simbolos()
    secciones = {}
    for p in pasos:
        secciones.setdefault(p["seccion"], []).append(p)

    for seccion, items in secciones.items():
        st.subheader(seccion)
        for item in items:
            st.code(item["codigo"], language="python")
            if item["seccion"] == "Árbol de ámbitos final":
                st.code(item["resultado"], language="text")
            else:
                st.success(item["resultado"])