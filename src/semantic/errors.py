"""
Recolector de errores semánticos.

El análisis no se detiene en el primer error: cada regla reporta aquí y el
recorrido continúa. Los mensajes idénticos en la misma posición se guardan una
sola vez, para no repetir el mismo error durante la recuperación.
"""

from __future__ import annotations


class SemanticIssue:
    """Un error semántico con su posición en el archivo fuente."""

    def __init__(self, message: str, line: int = 0, column: int = 0):
        self.message = message
        self.line = line
        self.column = column

    def __str__(self):
        return f"[línea {self.line}:{self.column}] {self.message}"

    def __repr__(self):
        return f"SemanticIssue({self.message!r}, line={self.line}, column={self.column})"


def position(node) -> tuple[int, int]:
    """(línea, columna) de un contexto de ANTLR, un token o una tupla (l, c)."""
    if node is None:
        return (0, 0)
    if isinstance(node, tuple):
        return node
    token = getattr(node, "start", node)  # ParserRuleContext -> token inicial
    return (getattr(token, "line", 0), getattr(token, "column", 0))


class ErrorCollector:
    """Acumula los errores de una ejecución completa del análisis."""

    def __init__(self):
        self._issues: list[SemanticIssue] = []
        self._seen: set[tuple[int, int, str]] = set()

    def add(self, message: str, node=None) -> None:
        line, column = position(node)
        key = (line, column, message)
        if key in self._seen:
            return
        self._seen.add(key)
        self._issues.append(SemanticIssue(message, line, column))

    @property
    def issues(self) -> list[SemanticIssue]:
        return sorted(self._issues, key=lambda i: (i.line, i.column))

    @property
    def has_errors(self) -> bool:
        return bool(self._issues)

    def as_text(self) -> str:
        return "\n".join(str(issue) for issue in self.issues)

    def __len__(self):
        return len(self._issues)

    def __iter__(self):
        return iter(self.issues)
