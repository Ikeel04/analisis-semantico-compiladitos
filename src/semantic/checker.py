"""
Reglas semánticas de Compiscript: sistema de tipos, funciones y control de flujo.

Se usa desde el Visitor de ANTLR. Ningún método lanza excepciones: reportan en
el ErrorCollector y devuelven un tipo (ERROR cuando fallan) para que el
recorrido continúe y se acumulen varios errores en una sola ejecución.

El parámetro `node` de cada método es el contexto de ANTLR del que se toma la
posición del error; puede ser None en las pruebas.
"""

from __future__ import annotations

import type_system as ts
from errors import ErrorCollector
from symbol_table import SemanticError, Symbol, SymbolTable


class _FunctionFrame:
    """Estado de la función que se está recorriendo."""

    def __init__(self, symbol: Symbol):
        self.symbol = symbol
        self.returned_value = False
        self.captured: set[str] = set()


class SemanticChecker:
    def __init__(self, table: SymbolTable | None = None,
                 errors: ErrorCollector | None = None,
                 is_subclass=None):
        self.table = table or SymbolTable()
        self.errors = errors or ErrorCollector()
        self.is_subclass = is_subclass          # hook de herencia (clases)
        self._functions: list[_FunctionFrame] = []
        self._loop_depth: list[int] = [0]       # un contador por función

    def _fail(self, message: str, node) -> str:
        self.errors.add(message, node)
        return ts.ERROR

    def _insert(self, name: str, kind: str, type_, node, **extra) -> Symbol | None:
        try:
            return self.table.insert(name, kind, type_, **extra)
        except SemanticError as exc:
            self.errors.add(str(exc), node)
            return None

    # Sistema de tipos: operadores

    def arithmetic(self, op: str, left, right, node=None) -> str:
        result = ts.arithmetic(op, left, right)
        if result is None:
            return self._fail(
                f"no se puede aplicar '{op}' entre '{ts.name(left)}' y '{ts.name(right)}'", node)
        return result

    def logical(self, op: str, left, right, node=None) -> str:
        result = ts.logical(op, left, right)
        if result is None:
            return self._fail(
                f"'{op}' requiere operandos boolean, recibió "
                f"'{ts.name(left)}' y '{ts.name(right)}'", node)
        return result

    def comparison(self, op: str, left, right, node=None) -> str:
        result = ts.comparison(op, left, right, self.is_subclass)
        if result is None:
            return self._fail(
                f"no se puede comparar '{ts.name(left)}' con '{ts.name(right)}' usando '{op}'", node)
        return result

    def unary(self, op: str, operand, node=None) -> str:
        result = ts.unary(op, operand)
        if result is None:
            expected = "boolean" if op == "!" else "numérico"
            return self._fail(
                f"'{op}' requiere un operando {expected}, recibió '{ts.name(operand)}'", node)
        return result

    def array_literal(self, element_types: list, node=None) -> str:
        element = ts.unify(element_types)
        if element is None:
            return self._fail("los elementos del arreglo deben ser del mismo tipo", node)
        return ts.array_of(element)
    
    # Sistema de tipos: declaraciones y asignaciones

    def check_compatible(self, target_type, value_type, label: str, node=None) -> bool:
        """Chequeo genérico de asignación, reutilizable para atributos e índices."""
        if ts.assignable(target_type, value_type, self.is_subclass):
            return True
        self._fail(
            f"{label}: se esperaba '{ts.name(target_type)}' y se recibió '{ts.name(value_type)}'",
            node)
        return False

    def declare_variable(self, name: str, declared_type=None, value_type=None, node=None):
        """let / var. Devuelve el tipo efectivo, o None si queda por inferir."""
        effective = declared_type
        if declared_type is not None and value_type is not None:
            self.check_compatible(declared_type, value_type,
                                  f"no se puede inicializar '{name}'", node)
        elif declared_type is None and value_type not in (None, ts.NULL):
            effective = value_type      # tipo inferido del inicializador
        self._insert(name, "variable", effective, node,
                     is_initialized=value_type is not None)
        return effective

    def declare_constant(self, name: str, declared_type=None, value_type=None,
                         node=None, has_initializer: bool = True):
        """const: la inicialización es obligatoria en la declaración."""
        if not has_initializer:
            self.errors.add(f"la constante '{name}' debe inicializarse en su declaración", node)
        elif declared_type is not None:
            self.check_compatible(declared_type, value_type,
                                  f"no se puede inicializar la constante '{name}'", node)
        effective = declared_type if declared_type is not None else value_type
        self._insert(name, "constant", effective, node, is_initialized=has_initializer)
        return effective

    def check_assignment(self, name: str, value_type, node=None) -> str:
        symbol = self.table.lookup(name)
        if symbol is None:
            return self._fail(f"'{name}' no ha sido declarado", node)
        if symbol.kind == "constant":
            return self._fail(f"no se puede reasignar la constante '{name}'", node)
        if symbol.kind == "function":
            return self._fail(f"no se puede asignar a la función '{name}'", node)
        if symbol.type is None:                 # declarada sin tipo: se infiere aquí
            self.table.update(name, type_=value_type, is_initialized=True)
            return value_type
        if not self.check_compatible(symbol.type, value_type,
                                     f"no se puede asignar a '{name}'", node):
            return ts.ERROR
        self.table.update(name, is_initialized=True)
        return symbol.type

    def use_variable(self, name: str, node=None) -> str:
        """Tipo de un identificador usado en una expresión.

        Recorre la cadena de ámbitos a mano para registrar las variables que la
        función actual toma de un entorno exterior (closures).
        """
        scope = self.table.current
        crossed_function = False
        while scope is not None:
            symbol = scope.resolve_local(name)
            if symbol is not None:
                if crossed_function and symbol.kind != "function" and self._functions:
                    self._functions[-1].captured.add(name)
                return symbol.type if symbol.type is not None else ts.ERROR
            crossed_function = crossed_function or scope.kind == "function"
            scope = scope.parent
        return self._fail(f"'{name}' no ha sido declarado", node)

    # Funciones

    def declare_function(self, name: str, params: list, return_type=None, node=None) -> Symbol:
        """Declara la función en el ámbito actual ANTES de recorrer su cuerpo,
        para que pueda llamarse a sí misma (recursión).

        params: lista de tuplas (nombre, tipo). Para las funciones, symbol.type
        guarda el tipo de retorno y symbol.extra['params'] la firma.
        """
        return_type = return_type or ts.VOID
        if self.table.lookup_local(name) is not None:
            self.errors.add(
                f"'{name}' ya fue declarado en este ámbito; Compiscript no permite sobrecarga",
                node)
            return Symbol(name, "function", return_type, params=params)
        return self.table.insert(name, "function", return_type, params=params)

    def enter_function(self, symbol: Symbol, node=None) -> None:
        """Abre el ámbito de la función y declara sus parámetros.

        El ámbito cuelga del ámbito donde se declaró la función, así que una
        función anidada resuelve por la cadena de ámbitos las variables del
        entorno que la contiene.
        """
        self.table.enter_scope("function", name=symbol.name)
        for param_name, param_type in symbol.extra.get("params", []):
            self._insert(param_name, "parameter", param_type, node, is_initialized=True)
        self._functions.append(_FunctionFrame(symbol))
        self._loop_depth.append(0)   # break/continue no cruzan la frontera de la función

    def exit_function(self, node=None) -> None:
        frame = self._functions.pop()
        self._loop_depth.pop()
        self.table.exit_scope()
        frame.symbol.extra["captured"] = sorted(frame.captured)
        expected = frame.symbol.type
        if not ts.is_error(expected) and expected != ts.VOID and not frame.returned_value:
            self.errors.add(
                f"la función '{frame.symbol.name}' debe retornar un valor de tipo '{expected}'",
                node)

    def check_call(self, name: str, arg_types: list, node=None) -> str:
        symbol = self.table.lookup(name)
        if symbol is None:
            return self._fail(f"'{name}' no ha sido declarado", node)
        if symbol.kind != "function":
            return self._fail(f"'{name}' no es una función y no puede llamarse", node)
        return self.check_arguments(symbol, arg_types, node)

    def check_arguments(self, symbol: Symbol, arg_types: list, node=None) -> str:
        """Coincidencia posicional de argumentos. También sirve para métodos."""
        params = symbol.extra.get("params", [])
        if len(arg_types) != len(params):
            return self._fail(
                f"'{symbol.name}' espera {len(params)} argumento(s) y recibió {len(arg_types)}",
                node)
        for index, ((param_name, param_type), arg_type) in enumerate(zip(params, arg_types), 1):
            if param_type is not None:
                self.check_compatible(
                    param_type, arg_type,
                    f"argumento {index} ('{param_name}') de '{symbol.name}'", node)
        return symbol.type or ts.VOID

    def check_return(self, value_type=None, node=None) -> str:
        if not self._functions:
            return self._fail("'return' solo puede usarse dentro de una función", node)
        frame = self._functions[-1]
        expected = frame.symbol.type or ts.VOID
        if value_type is None:
            if expected != ts.VOID:
                self.errors.add(
                    f"'{frame.symbol.name}' debe retornar un valor de tipo '{expected}'", node)
            return ts.VOID
        frame.returned_value = True
        if expected == ts.VOID:
            return self._fail(
                f"'{frame.symbol.name}' no declara tipo de retorno y no puede retornar un valor",
                node)
        if not self.check_compatible(expected, value_type,
                                     f"el return de '{frame.symbol.name}'", node):
            return ts.ERROR
        return expected

    # ------------------------------------------------------------------
    # Control de flujo
    # ------------------------------------------------------------------

    def check_condition(self, condition_type, construct: str, node=None) -> str:
        """Condición de if, while, do-while y for."""
        if ts.is_error(condition_type):
            return ts.BOOLEAN
        if condition_type != ts.BOOLEAN:
            self.errors.add(
                f"la condición de '{construct}' debe ser boolean, no '{ts.name(condition_type)}'",
                node)
        return ts.BOOLEAN

    def check_switch_case(self, subject_type, case_type, node=None) -> None:
        """El switch no evalúa un boolean: cada 'case' debe ser comparable con
        la expresión que evalúa el switch."""
        if ts.comparison("==", subject_type, case_type, self.is_subclass) is None:
            self.errors.add(
                f"el 'case' de tipo '{ts.name(case_type)}' no es comparable con el "
                f"switch de tipo '{ts.name(subject_type)}'", node)

    def check_foreach(self, name: str, iterable_type, node=None):
        """foreach: la expresión debe ser un arreglo. Declara la variable del
        ciclo con el tipo de los elementos (llamar ya dentro del ámbito del bloque)."""
        if ts.is_error(iterable_type):
            element = ts.ERROR
        elif not ts.is_array(iterable_type):
            self._fail(f"'foreach' requiere un arreglo, no '{ts.name(iterable_type)}'", node)
            element = ts.ERROR
        else:
            element = ts.element_type(iterable_type)
        self._insert(name, "variable", element, node, is_initialized=True)
        return element

    def enter_loop(self) -> None:
        self._loop_depth[-1] += 1

    def exit_loop(self) -> None:
        self._loop_depth[-1] -= 1

    @property
    def in_loop(self) -> bool:
        return self._loop_depth[-1] > 0

    def check_break(self, node=None) -> None:
        if not self.in_loop:
            self.errors.add("'break' solo puede usarse dentro de un bucle", node)

    def check_continue(self, node=None) -> None:
        if not self.in_loop:
            self.errors.add("'continue' solo puede usarse dentro de un bucle", node)
