"""Dibujo del árbol sintáctico de Compiscript como imagen.

Convierte la estructura [texto, [hijos]] que produce analisis.py en una figura
de matplotlib con aspecto de editor de código (tema oscuro): los nodos internos
muestran el nombre de la regla gramatical y las hojas el token correspondiente.

    from arbol import figura_arbol

    fig = figura_arbol(resultado.arbol_estructura)
    st.pyplot(fig)
"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

COLOR_FONDO = "#1E1E1E"
COLOR_NODO_REGLA = "#2D2D2D"
COLOR_NODO_TOKEN = "#1E2A1E"
COLOR_BORDE_REGLA = "#569CD6"
COLOR_BORDE_TOKEN = "#6A9955"
COLOR_TEXTO = "#D4D4D4"
COLOR_ARISTA = "#6E7681"

LIMITE_TEXTO = 24
ANCHO_MAXIMO = 40


def _truncar(texto: str) -> str:
    texto = texto.replace("\n", "\\n")
    if len(texto) > LIMITE_TEXTO:
        return texto[: LIMITE_TEXTO - 3] + "..."
    return texto


def _layout(nodo, profundidad: int, siguiente_slot: list[int]) -> dict:
    """Calcula la posición (x, y) de cada nodo del árbol.

    Las hojas ocupan ranuras (slots) enteras consecutivas; cada nodo interno se
    centra entre sus hijos. La raíz queda arriba (y = 0).
    """
    texto, hijos = nodo
    if not hijos:
        x = siguiente_slot[0]
        siguiente_slot[0] += 1
        return {"x": x, "y": profundidad, "texto": texto, "hijos": []}
    layout_hijos = [_layout(hijo, profundidad + 1, siguiente_slot) for hijo in hijos]
    xs = [hijo["x"] for hijo in layout_hijos]
    return {
        "x": sum(xs) / len(xs),
        "y": profundidad,
        "texto": texto,
        "hijos": layout_hijos,
    }


def _medidas(nodo, profundidad: int, acumulador: list) -> None:
    """Cuenta hojas y profundidad máxima para dimensionar la figura."""
    _, hijos = nodo
    if not hijos:
        acumulador[0] += 1
        acumulador[1] = max(acumulador[1], profundidad)
        return
    for hijo in hijos:
        _medidas(hijo, profundidad + 1, acumulador)


def figura_arbol(estructura: list, dpi: int = 120):
    """Devuelve una figura matplotlib con el árbol sintáctico dibujado."""
    if not estructura:
        return None

    hojas = [0, 0]
    _medidas(estructura, 0, hojas)
    ancho = max(6.0, min(ANCHO_MAXIMO, 0.3 * hojas[0]))
    alto = max(4.0, 0.6 * (hojas[1] + 1))

    fig, ax = plt.subplots(figsize=(ancho, alto), dpi=dpi)
    fig.patch.set_facecolor(COLOR_FONDO)
    ax.set_facecolor(COLOR_FONDO)

    siguiente_slot = [0]
    raiz = _layout(estructura, 0, siguiente_slot)

    def dibujar_aristas(nodo) -> None:
        for hijo in nodo["hijos"]:
            ax.plot(
                [nodo["x"], hijo["x"]],
                [nodo["y"], hijo["y"]],
                color=COLOR_ARISTA,
                lw=1.0,
                solid_capstyle="round",
                zorder=1,
            )
            dibujar_aristas(hijo)

    def dibujar_nodos(nodo) -> None:
        es_hoja = not nodo["hijos"]
        ax.text(
            nodo["x"],
            nodo["y"],
            _truncar(nodo["texto"]),
            ha="center",
            va="center",
            fontsize=8 if es_hoja else 9,
            color=COLOR_TEXTO,
            bbox=dict(
                boxstyle="round,pad=0.35",
                fc=COLOR_NODO_TOKEN if es_hoja else COLOR_NODO_REGLA,
                ec=COLOR_BORDE_TOKEN if es_hoja else COLOR_BORDE_REGLA,
                lw=1.2,
            ),
            zorder=2,
        )
        for hijo in nodo["hijos"]:
            dibujar_nodos(hijo)

    dibujar_aristas(raiz)
    dibujar_nodos(raiz)

    ax.set_xlim(-0.5, siguiente_slot[0] - 0.5)
    ax.set_ylim(hojas[1] + 0.6, -0.6)  # Raíz arriba (y decrece hacia abajo).
    ax.axis("off")
    fig.tight_layout()
    return fig
