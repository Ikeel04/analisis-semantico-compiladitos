"""Interfaz gráfica de Compiscript con Streamlit.

Permite seleccionar un archivo .cps, escribir código directamente o cargar un
ejemplo, y ejecutar el análisis con el botón «Compilar». Los errores y el
árbol sintáctico se muestran en la interfaz (editor, pestañas), no en consola.

Uso:
    streamlit run app.py
"""

import html
import os
import sys
from pathlib import Path

# Módulos flat de src/: se agregan las carpetas al path como en los tests.
_BASE = Path(__file__).resolve().parent
for _carpeta in ("src/parser", "src/lexico", "src/compiler", "src/ide"):
    _ruta = str(_BASE / _carpeta)
    if _ruta not in sys.path:
        sys.path.insert(0, _ruta)

import streamlit as st

from arbol import figura_arbol
from pipeline import MENSAJE_EXITO, FilaError, ResultadoAnalisis, analizar_codigo
from analizador import Token

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
    st.caption("Analizador léxico y sintáctico")

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

tab_editor, tab_errores, tab_tokens, tab_arbol = st.tabs(
    ["Editor", "Errores", "Tokens", "Árbol"]
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
            "léxico(s) o sintáctico(s)."
        )
        st.dataframe(
            _tabla_de_errores(resultado.errores),
            width="stretch",
            hide_index=True,
        )

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

with tab_arbol:
    if resultado is None:
        st.info("Pulsa «Compilar» para construir el árbol sintáctico.")
    elif resultado.arbol_estructura:
        st.pyplot(figura_arbol(resultado.arbol_estructura), width="stretch")
        with st.expander("Ver el árbol como texto"):
            st.code(resultado.arbol, language="text")
    else:
        st.write("No se pudo construir el árbol sintáctico.")