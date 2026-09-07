"""
Tabla de símbolos y manejo de ámbitos para Compiscript.

Responsabilidad (Persona 1):
- Insertar / recuperar / actualizar símbolos.
- Crear un nuevo entorno (scope) por función, clase y bloque.
- Resolver nombres subiendo por la cadena de ámbitos (local -> global).
- Detectar variables no declaradas y redeclaraciones en el mismo ámbito.

Este módulo es independiente del parser generado por ANTLR: se integra
después desde el Visitor/Listener llamando a enter_scope()/exit_scope()
en cada nodo que abre un nuevo entorno (Program, FunctionDecl, ClassDecl,
Block) y a insert()/lookup()/update() en las declaraciones, usos y
asignaciones de identificadores.
"""

from __future__ import annotations


class SemanticError(Exception):
    """Error semántico relacionado con la tabla de símbolos o los ámbitos."""


class Symbol:
    """Un identificador declarado: variable, constante, función, parámetro o clase."""

    def __init__(self, name: str, kind: str, type_=None, **extra):
        self.name = name
        self.kind = kind          # "variable" | "constant" | "function" | "parameter" | "class"
        self.type = type_         # "integer", "string", "boolean", "Perro", "integer[]", etc.
        self.extra = extra        # info adicional: params, return_type, attributes, is_initialized...

    def __repr__(self):
        return f"Symbol(name={self.name!r}, kind={self.kind!r}, type={self.type!r}, extra={self.extra!r})"


class Scope:
    """Un entorno de símbolos: global, de función, de clase o de bloque."""

    def __init__(self, kind: str, parent: "Scope | None" = None, name: str | None = None):
        self.kind = kind          # "global" | "function" | "class" | "block"
        self.parent = parent
        self.name = name          # nombre de la función/clase dueña del scope, si aplica
        self.symbols: dict[str, Symbol] = {}
        self.children: list["Scope"] = []

    def declare_here(self, symbol: Symbol) -> None:
        """Inserta en ESTE ámbito. Lanza error si ya existe (redeclaración)."""
        if symbol.name in self.symbols:
            raise SemanticError(
                f"'{symbol.name}' ya fue declarado en este ámbito ({self.kind})"
            )
        self.symbols[symbol.name] = symbol

    def resolve_local(self, name: str) -> Symbol | None:
        return self.symbols.get(name)

    def __repr__(self):
        return f"Scope(kind={self.kind!r}, name={self.name!r}, symbols={list(self.symbols)})"


class SymbolTable:
    """API pública que va a usar el resto del equipo desde el Visitor de ANTLR."""

    def __init__(self):
        self.global_scope = Scope(kind="global", name="global")
        self.current = self.global_scope

    # ---------- manejo de ámbitos ----------

    def enter_scope(self, kind: str, name: str | None = None) -> Scope:
        """Crea y entra a un nuevo entorno hijo del actual.
        kind: 'function' | 'class' | 'block'
        """
        new_scope = Scope(kind=kind, parent=self.current, name=name)
        self.current.children.append(new_scope)
        self.current = new_scope
        return new_scope

    def exit_scope(self) -> None:
        """Regresa al ámbito padre. Debe llamarse al terminar de visitar
        el nodo que abrió el scope (fin de función, clase o bloque)."""
        if self.current.parent is None:
            raise RuntimeError("No se puede salir del ámbito global")
        self.current = self.current.parent

    # ---------- insertar / recuperar / actualizar ----------

    def insert(self, name: str, kind: str, type_=None, **extra) -> Symbol:
        """Declara un símbolo en el ámbito ACTUAL. Detecta redeclaración."""
        symbol = Symbol(name, kind, type_, **extra)
        self.current.declare_here(symbol)
        return symbol

    def lookup(self, name: str) -> Symbol | None:
        """Busca desde el ámbito actual hacia arriba (local -> global).
        Devuelve None si no existe -> úsalo para reportar 'variable no declarada'."""
        scope = self.current
        while scope is not None:
            found = scope.resolve_local(name)
            if found is not None:
                return found
            scope = scope.parent
        return None

    def lookup_local(self, name: str) -> Symbol | None:
        """Busca SOLO en el ámbito actual (útil para chequear redeclaración
        antes de insertar, sin lanzar excepción)."""
        return self.current.resolve_local(name)

    def update(self, name: str, **fields) -> Symbol:
        """Actualiza un símbolo ya declarado (ej. tipo inferido, marcar como
        inicializado). Lanza error si no existe."""
        symbol = self.lookup(name)
        if symbol is None:
            raise SemanticError(f"No se puede actualizar '{name}': no ha sido declarado")
        for key, value in fields.items():
            if key == "type_":
                symbol.type = value
            elif key == "kind":
                symbol.kind = value
            else:
                symbol.extra[key] = value
        return symbol

    # ---------- utilidades para el IDE / árbol visual ----------

    def describe_tree(self, scope: Scope | None = None, indent: int = 0) -> str:
        """Representación en texto del árbol de ámbitos, útil para debug
        o como base de la visualización en el IDE."""
        scope = scope or self.global_scope
        pad = "  " * indent
        header = f"{pad}[{scope.kind}]" + (f" {scope.name}" if scope.name else "")
        lines = [header]
        for sym_name, sym in scope.symbols.items():
            lines.append(f"{pad}  - {sym_name}: {sym.kind} ({sym.type})")
        for child in scope.children:
            lines.append(self.describe_tree(child, indent + 1))
        return "\n".join(lines)

    def filas_para_ide(self, scope: Scope | None = None, profundidad: int = 0) -> list[dict]:
        """Filas para la pestaña «Ámbitos» del IDE: una fila por ámbito, con sus
        símbolos y el tipo de cada uno. La sangría del texto indica la jerarquía."""
        scope = scope or self.global_scope
        filas = []
        etiqueta = ("  " * profundidad) + f"[{scope.kind}]"
        if scope.name:
            etiqueta += f" {scope.name}"
        simbolos = "; ".join(
            f"{nombre} ({sym.kind} · {sym.type})"
            for nombre, sym in sorted(scope.symbols.items())
        ) or "—"
        filas.append({"Ámbito": etiqueta, "Símbolos": simbolos})
        for hijo in scope.children:
            filas += self.filas_para_ide(hijo, profundidad + 1)
        return filas
