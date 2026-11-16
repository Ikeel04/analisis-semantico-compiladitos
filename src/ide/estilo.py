"""
Tema visual del IDE: «dragón de fuego» (guiño al Dragon Book).

- `inyectar_tema()`: CSS de toda la app (fondo con brillos, pestañas,
  métricas como tarjetas, botones, editor).
- `marca_lateral()`: dragón pequeño y nombre en la barra lateral.
- `encabezado(resultado)`: banner con el dragón y la barra de fases
  (léxico → sintáctico → semántico → TAC → MIPS), que se enciende hasta donde
  llegó la compilación y marca en rojo la fase con errores.

El dragón es un SVG propio, dibujado aquí; no usa imágenes externas.
"""

from __future__ import annotations

import streamlit as st

# Paleta
FONDO = "#120E18"
PANEL = "#1C1526"
BORDE = "rgba(181, 123, 255, 0.18)"
VIOLETA = "#B57BFF"
VIOLETA_OSCURO = "#7B3FE4"
BRASA = "#FF7A2F"
ORO = "#FFB020"
TEXTO = "#ECE6F5"

FASES = ["Léxico", "Sintáctico", "Semántico", "Código intermedio", "MIPS"]


def dragon_svg(prefijo: str = "d", ancho: int = 260) -> str:
    """Dragón violeta que echa fuego con código. `prefijo` separa los ids de
    los gradientes cuando hay más de un dragón en la página."""
    p = prefijo
    return (
        f'<svg class="dragon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 260 170" '
        f'width="{ancho}" role="img" aria-label="Dragón de Compiscript">'
        f'<defs>'
        f'<linearGradient id="{p}esc" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="#B57BFF"/><stop offset="0.55" stop-color="#7B3FE4"/>'
        f'<stop offset="1" stop-color="#3D1A7A"/></linearGradient>'
        f'<linearGradient id="{p}ala" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="#5B2BB0" stop-opacity="0.95"/>'
        f'<stop offset="1" stop-color="#2A1150" stop-opacity="0.9"/></linearGradient>'
        f'<linearGradient id="{p}fue" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0" stop-color="#FFE27A"/><stop offset="0.45" stop-color="#FF8A2B"/>'
        f'<stop offset="1" stop-color="#FF3D57" stop-opacity="0"/></linearGradient>'
        f'<radialGradient id="{p}ojo" cx="0.5" cy="0.5" r="0.5">'
        f'<stop offset="0" stop-color="#FFF6B0"/><stop offset="1" stop-color="#FFB020"/>'
        f'</radialGradient></defs>'
        f'<g class="ala">'
        f'<path d="M70 92 C 60 50, 30 30, 8 28 C 22 40, 24 52, 20 62 C 30 58, 40 62, 44 70 '
        f'C 34 70, 28 78, 28 86 C 40 80, 54 84, 62 98 Z" fill="url(#{p}ala)" stroke="#B57BFF" '
        f'stroke-width="1.2" stroke-linejoin="round"/>'
        f'<path d="M70 92 L 20 62 M70 92 L 28 86 M70 92 L 8 28" stroke="#B57BFF" '
        f'stroke-width="1" opacity="0.6"/></g>'
        f'<path d="M60 120 C 30 130, 20 150, 40 158 C 56 164, 70 150, 60 142 C 54 138, 46 144, 50 150" '
        f'fill="none" stroke="url(#{p}esc)" stroke-width="9" stroke-linecap="round"/>'
        f'<path d="M48 152 l -8 6 l 10 1 z" fill="#B57BFF"/>'
        f'<path d="M58 124 C 56 100, 72 86, 92 84 C 112 82, 118 100, 112 118 C 104 138, 66 142, 58 124 Z" '
        f'fill="url(#{p}esc)"/>'
        f'<path d="M74 126 C 78 110, 92 100, 106 104" fill="none" stroke="#E9D7FF" stroke-width="5" '
        f'stroke-linecap="round" opacity="0.55"/>'
        f'<path d="M96 90 C 104 70, 116 58, 132 52 L 142 64 C 128 70, 118 82, 112 100 Z" fill="url(#{p}esc)"/>'
        f'<path d="M98 86 l 2 -10 l 5 8 Z M106 74 l 3 -10 l 4 9 Z M116 64 l 4 -9 l 3 9 Z '
        f'M64 104 l -4 -9 l 9 4 Z M74 92 l -1 -10 l 8 6 Z" fill="#FFB020"/>'
        f'<path d="M128 50 C 136 38, 154 34, 168 40 L 186 46 C 192 48, 192 54, 186 56 L 168 58 '
        f'L 182 64 C 186 66, 184 72, 178 71 L 160 68 C 150 70, 140 68, 136 62 Z" fill="url(#{p}esc)"/>'
        f'<path d="M146 40 C 140 26, 132 20, 122 18 C 132 26, 136 34, 138 44 Z" fill="#FFD27A"/>'
        f'<path d="M156 37 C 154 26, 150 18, 142 12 C 150 22, 150 30, 150 38 Z" fill="#FFB020"/>'
        f'<ellipse cx="158" cy="46" rx="4.5" ry="3.2" fill="url(#{p}ojo)"/>'
        f'<ellipse cx="159" cy="46" rx="1.1" ry="2.6" fill="#2A1150"/>'
        f'<circle cx="182" cy="50" r="1.3" fill="#2A1150"/>'
        f'<path d="M172 58 l 2 4 l 2 -4 Z M178 58 l 2 4 l 2 -4 Z" fill="#FFF"/>'
        f'<g class="fuego">'
        f'<path d="M186 60 C 200 54, 214 58, 226 52 C 220 60, 236 62, 252 58 C 238 68, 222 70, 210 74 '
        f'C 220 78, 232 80, 240 86 C 220 86, 200 80, 184 68 Z" fill="url(#{p}fue)"/>'
        f'<g font-family="Consolas, Menlo, monospace" font-weight="700" fill="#FFF3C4">'
        f'<text x="200" y="66" font-size="9">{{ }}</text>'
        f'<text x="222" y="62" font-size="7" opacity="0.8">;</text>'
        f'<text x="214" y="78" font-size="7" opacity="0.7">01</text></g></g>'
        f'<path d="M100 128 l 6 12 l 8 -2" fill="none" stroke="#7B3FE4" stroke-width="6" '
        f'stroke-linecap="round" stroke-linejoin="round"/>'
        f'<path d="M74 132 l 2 12 l 8 0" fill="none" stroke="#5B2BB0" stroke-width="6" '
        f'stroke-linecap="round" stroke-linejoin="round"/>'
        f'</svg>'
    )


_CSS = f"""
<style>
/* ---------- fondo y estructura ---------- */
.stApp {{
    background:
        radial-gradient(900px 420px at 92% -8%, rgba(123, 63, 228, 0.22), transparent 60%),
        radial-gradient(700px 380px at -10% 108%, rgba(255, 122, 47, 0.12), transparent 60%),
        {FONDO};
}}
[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stSidebar"] {{
    background: linear-gradient(180deg, #1B1226 0%, {FONDO} 100%);
    border-right: 1px solid {BORDE};
}}
.block-container {{ padding-top: 2.2rem; }}

/* ---------- encabezado ---------- */
.cs-banner {{
    display: flex; align-items: center; justify-content: space-between; gap: 24px;
    padding: 18px 26px; margin-bottom: 14px;
    border: 1px solid {BORDE}; border-radius: 18px;
    background:
        linear-gradient(120deg, rgba(123, 63, 228, 0.20), rgba(255, 122, 47, 0.08) 70%),
        {PANEL};
    box-shadow: 0 10px 40px rgba(0, 0, 0, 0.35), inset 0 1px 0 rgba(255, 255, 255, 0.04);
    position: relative; overflow: hidden;
}}
.cs-banner::after {{
    content: ""; position: absolute; inset: auto -40px -60px auto; width: 260px; height: 160px;
    background: radial-gradient(closest-side, rgba(255, 122, 47, 0.25), transparent);
    pointer-events: none;
}}
.cs-kicker {{
    font-size: 11px; letter-spacing: 0.18em; text-transform: uppercase;
    color: {VIOLETA}; font-weight: 700; margin-bottom: 2px;
}}
.cs-titulo {{
    font-size: 44px; line-height: 1.05; font-weight: 800; margin: 0;
    background: linear-gradient(90deg, #FFE27A, {BRASA} 45%, #FF3D57 75%, {VIOLETA});
    -webkit-background-clip: text; background-clip: text; color: transparent;
}}
.cs-sub {{ color: #BFB3D1; font-size: 14px; margin: 6px 0 14px 0; }}
.cs-fases {{ display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }}
.cs-fase {{
    font-size: 12px; font-weight: 600; padding: 4px 11px; border-radius: 999px;
    border: 1px solid rgba(255, 255, 255, 0.10); color: #8E8299;
    background: rgba(255, 255, 255, 0.03);
}}
.cs-fase.ok {{
    color: #1B1006; border-color: transparent;
    background: linear-gradient(90deg, {ORO}, {BRASA});
    box-shadow: 0 0 12px rgba(255, 122, 47, 0.45);
}}
.cs-fase.error {{
    color: #FFD0D0; border-color: rgba(255, 80, 80, 0.6); background: rgba(255, 61, 87, 0.18);
}}
.cs-fase.bloqueada {{ opacity: 0.45; text-decoration: line-through; }}
.cs-flecha {{ color: #5E5070; font-size: 12px; }}
.cs-banner .dragon {{ flex-shrink: 0; animation: cs-flotar 5s ease-in-out infinite; }}
.cs-banner .fuego {{ transform-origin: 186px 64px; animation: cs-llama 1.6s ease-in-out infinite; }}
@keyframes cs-flotar {{ 0%, 100% {{ transform: translateY(0); }} 50% {{ transform: translateY(-6px); }} }}
@keyframes cs-llama {{
    0%, 100% {{ transform: scaleX(1); opacity: 1; }}
    50% {{ transform: scaleX(0.86); opacity: 0.8; }}
}}
@media (prefers-reduced-motion: reduce) {{
    .cs-banner .dragon, .cs-banner .fuego {{ animation: none; }}
}}
@media (max-width: 900px) {{ .cs-banner .dragon {{ display: none; }} }}

/* ---------- barra lateral ---------- */
.cs-marca {{ display: flex; align-items: center; gap: 10px; margin: -8px 0 6px 0; }}
.cs-marca .nombre {{
    font-size: 22px; font-weight: 800;
    background: linear-gradient(90deg, #FFE27A, {BRASA});
    -webkit-background-clip: text; background-clip: text; color: transparent;
}}
.cs-marca .lema {{ font-size: 11px; color: #9C8FB0; }}

/* ---------- pestañas ---------- */
[data-testid="stTabs"] [data-baseweb="tab-list"] {{
    gap: 2px; border-bottom: 1px solid {BORDE};
}}
[data-testid="stTabs"] button p {{ font-weight: 600; color: #A99CBB; }}
[data-testid="stTabs"] button:hover p {{ color: {TEXTO}; }}
[data-testid="stTabs"] button[aria-selected="true"] p {{ color: {ORO}; }}
[data-testid="stTabs"] [data-baseweb="tab-highlight"] {{
    background: linear-gradient(90deg, {ORO}, {BRASA}); height: 3px; border-radius: 3px;
}}

/* ---------- métricas como tarjetas ---------- */
[data-testid="stMetric"] {{
    background: linear-gradient(160deg, rgba(123, 63, 228, 0.12), rgba(255, 255, 255, 0.02));
    border: 1px solid {BORDE}; border-radius: 14px; padding: 14px 18px;
}}
[data-testid="stMetricLabel"] p {{ color: #B9ACCB; font-weight: 600; }}
[data-testid="stMetricValue"] {{ color: #FFD9A0; }}

/* ---------- títulos ---------- */
h2, h3 {{ color: #EADCFF !important; }}
[data-testid="stMarkdownContainer"] h2, [data-testid="stMarkdownContainer"] h3 {{
    border-left: 4px solid {BRASA}; padding-left: 10px;
}}

/* ---------- botones ---------- */
.stButton > button {{
    border-radius: 10px; border: 1px solid {BORDE}; background: rgba(255, 255, 255, 0.03);
    transition: transform 0.08s ease, box-shadow 0.2s ease, border-color 0.2s ease;
}}
.stButton > button:hover {{ border-color: {VIOLETA}; box-shadow: 0 0 14px rgba(181, 123, 255, 0.25); }}
.stButton > button[kind="primary"] {{
    background: linear-gradient(90deg, {ORO}, {BRASA} 55%, #FF3D57); color: #1B1006;
    border: none; font-weight: 800; box-shadow: 0 4px 18px rgba(255, 122, 47, 0.35);
}}
.stButton > button[kind="primary"]:hover {{ transform: translateY(-1px); box-shadow: 0 6px 24px rgba(255, 122, 47, 0.55); }}
.stButton > button[kind="primary"] p {{ color: #1B1006; font-weight: 800; }}

/* ---------- editor ---------- */
[data-testid="stTextArea"] {{ border-radius: 12px; overflow: hidden; }}
[data-testid="stTextArea"] textarea {{
    background-color: #17111F; color: #E6DFF0;
    font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, "Liberation Mono", monospace;
    font-size: 14px; line-height: 1.6;
    border: 1px solid {BORDE}; border-radius: 12px; caret-color: {BRASA};
}}
[data-testid="stTextArea"] textarea:focus {{
    border-color: {BRASA}; box-shadow: 0 0 0 1px {BRASA}, 0 0 18px rgba(255, 122, 47, 0.25);
}}

/* ---------- código, tablas y avisos ---------- */
[data-testid="stCode"], [data-testid="stCodeBlock"] {{ border: 1px solid {BORDE}; border-radius: 12px; }}
[data-testid="stDataFrame"] {{ border: 1px solid {BORDE}; border-radius: 12px; overflow: hidden; }}
[data-testid="stAlert"] {{ border-radius: 12px; }}
[data-testid="stExpander"] details {{ border: 1px solid {BORDE}; border-radius: 12px; }}

/* ---------- barra del archivo ---------- */
.barra-archivo {{ display: flex; align-items: center; gap: 8px; padding: 2px 0 10px 0; }}
.chip-archivo {{
    font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace; font-size: 13px;
    color: {TEXTO}; background-color: {PANEL}; border: 1px solid {BORDE};
    border-radius: 8px; padding: 3px 10px;
}}
.chip-estado {{ font-size: 12px; font-weight: 700; border-radius: 12px; padding: 3px 12px; }}
.chip-estado.sin-analizar {{ background-color: #2A2233; color: #CFC4DD; }}
.chip-estado.valido      {{ background-color: #1F4A2A; color: #8FE3A0; box-shadow: 0 0 10px rgba(80, 220, 120, 0.25); }}
.chip-estado.con-errores {{ background-color: #5A2230; color: #FFB0B8; box-shadow: 0 0 10px rgba(255, 61, 87, 0.25); }}
</style>
"""


def inyectar_tema() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def marca_lateral() -> None:
    st.markdown(
        '<div class="cs-marca">' + dragon_svg("m", 64)
        + '<div><div class="nombre">Compiscript</div>'
        '<div class="lema">del código fuente a MIPS</div></div></div>',
        unsafe_allow_html=True,
    )


def estados_de_fases(resultado) -> list[str]:
    """'ok', 'error', 'bloqueada' o '' (sin analizar) para cada fase de FASES."""
    if resultado is None:
        return [""] * len(FASES)
    tipos = {e.tipo for e in resultado.errores}
    if tipos:
        # Las fases sin errores después de una que falló quedan neutras: no
        # se pueden dar por buenas si la entrada ya venía rota.
        estados, fallo = [], False
        for t in ("Léxico", "Sintáctico", "Semántico"):
            if t in tipos:
                estados.append("error")
                fallo = True
            else:
                estados.append("" if fallo else "ok")
        return estados + ["bloqueada", "bloqueada"]
    estados = ["ok", "ok", "ok"]
    return estados + ["ok" if resultado.genero_tac else "bloqueada",
                      "ok" if resultado.genero_asm else "bloqueada"]


def encabezado(resultado) -> None:
    """Banner con el dragón y la barra de fases. `resultado` es None si no se
    ha compilado (o si el código cambió desde la última compilación)."""
    piezas = []
    for i, (fase, estado) in enumerate(zip(FASES, estados_de_fases(resultado))):
        if i:
            piezas.append('<span class="cs-flecha">➜</span>')
        piezas.append(f'<span class="cs-fase {estado}">{fase}</span>')
    st.markdown(
        '<div class="cs-banner"><div>'
        '<div class="cs-kicker">Construcción de Compiladores · UVG</div>'
        '<div class="cs-titulo">Compiscript</div>'
        '<div class="cs-sub">Análisis léxico, sintáctico y semántico, código de tres '
        'direcciones y ensamblador MIPS32 listo para MARS.</div>'
        f'<div class="cs-fases">{"".join(piezas)}</div>'
        '</div>' + dragon_svg("b", 250) + '</div>',
        unsafe_allow_html=True,
    )


def dot_con_tema(dot: str) -> str:
    """Pone el árbol de activación (DOT) con los colores del tema: fondo
    transparente, nodos violeta y flechas color brasa. Se dibuja de izquierda
    a derecha: los árboles de activación suelen ser anchos (muchas llamadas
    desde main) y así se leen sin achicarse."""
    return dot.replace(
        "digraph activacion {",
        'digraph activacion {\n  bgcolor="transparent";\n  rankdir=LR;\n  nodesep=0.12;', 1,
    ).replace(
        'fillcolor="#EAF2FB", color="#569CD6", fontname="Helvetica"',
        'fillcolor="#2A1E3A", color="#B57BFF", fontcolor="#F1E8FF", fontname="Helvetica"',
    ).replace('edge [color="#8A8A8A"]', 'edge [color="#FF7A2F", arrowsize=0.7]')
