"""
Listener semántico de Compiscript.

Recorre el árbol que genera ANTLR (regla `program`) y traduce cada nodo a una
llamada al SemanticChecker. El checker acumula los errores en un ErrorCollector
sin detenerse, de modo que una sola pasada reporta todos los errores.

El listener va de abajo hacia arriba (ANTLR visita primero los hijos): cada
nodo de expresión guarda su tipo en `tipo_de` al salir, usando como clave el
id() del contexto. Los identificadores se guardan primero como el marcador
("id", nombre) y se resuelven (use_variable) de forma perezosa cuando el nodo
padre pide el tipo, así un nombre se reporta una sola vez.

Para las asignaciones el listener guarda en `_destino`, por cada leftHandSide,
cómo se escribió: ("id", nombre), ("indice", contenedor, índice) o
("propiedad", tipo_objeto, miembro). exitAssignExpr / exitAssignment / 
exitPropertyAssignExpr lo consumen para validar el objetivo.
"""

from __future__ import annotations

import os
import sys

# El proyecto usa imports flat (igual que los tests): se añade cada paquete a
# sys.path para poder importar 'type_system', 'checker', etc. sin prefijos.
_AQUI = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.dirname(_AQUI)
for _paquete in ("parser", "semantic"):
    _ruta = os.path.join(_SRC, _paquete)
    if _ruta not in sys.path:
        sys.path.insert(0, _ruta)

from generated.CompiscriptParser import CompiscriptParser
from generated.CompiscriptListener import CompiscriptListener
import type_system as ts
from checker import SemanticChecker


class SemanticListener(CompiscriptListener):
    def __init__(self, checker: SemanticChecker | None = None):
        self.checker = checker or SemanticChecker()
        self.tipo_de: dict[int, object] = {}      # tipo por nodo de expresión
        self._nombres: dict[int, str] = {}        # nombre de cada identificador
        self._destino: dict[int, tuple] = {}      # cómo se asigna cada lhs
        self._secuencias: list[bool] = []         # flujo terminado por lista de sentencias

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    def _tipo_anotacion(self, tipo_ctx):
        """El texto de una anotación de tipo ('integer', 'Perro', 'integer[]')."""
        return tipo_ctx.getText() if tipo_ctx is not None else None

    def _operadores(self, ctx, ops: set) -> list:
        return [h.getText() for h in ctx.getChildren()
                if getattr(h, "getSymbol", None) is not None
                and h.getSymbol().text in ops]

    def _tipos(self, args_ctx) -> list:
        """Tipos de los argumentos de una llamada."""
        if args_ctx is None:
            return []
        return [self._tipo_de(e) for e in args_ctx.expression()]

    def _es_cuerpo_de_funcion(self, ctx) -> bool:
        """El bloque que abre el ámbito de una función (ya abierto por el checker)."""
        return isinstance(ctx.parentCtx, CompiscriptParser.FunctionDeclarationContext)

    def _tipo_de(self, expr):
        """Tipo memoizado de un nodo; resuelve los identificadores pendientes."""
        valor = self.tipo_de.get(id(expr))
        if isinstance(valor, tuple) and len(valor) == 2 and valor[0] == "id":
            tipo = self.checker.use_variable(valor[1], expr)
            self.tipo_de[id(expr)] = tipo
            return tipo
        return valor if valor is not None else ts.ERROR

    def _plegar(self, ctx, hijos, ops, metodo) -> None:
        """Tipa una cadena de operadores binarios de izquierda a derecha."""
        tipos = [self._tipo_de(h) for h in hijos]
        for i, op in enumerate(ops):
            tipos[i + 1] = metodo(op, tipos[i], tipos[i + 1], ctx)
        self.tipo_de[id(ctx)] = tipos[-1]

    def _terminar_secuencia(self) -> None:
        """Marca la lista de sentencias actual como terminada (return/break/continue)."""
        if self._secuencias:
            self._secuencias[-1] = True

    def _condicion(self, ctx_expr, constructo: str):
        """Tipa una condición y, si es un literal verdadero/falso, lo reporta."""
        if ctx_expr.getText() in ("true", "false"):
            self.checker.errors.add(
                f"la condición de '{constructo}' es una constante "
                f"('{ctx_expr.getText()}')", ctx_expr)
        return self.checker.check_condition(self._tipo_de(ctx_expr), constructo,
                                            ctx_expr)

    # ------------------------------------------------------------------
    # Programa y secuencias de sentencias (código inalcanzable)
    # ------------------------------------------------------------------

    def enterProgram(self, ctx):
        self._secuencias.append(False)

    def exitProgram(self, ctx):
        self._secuencias.pop()

    def enterStatement(self, ctx):
        if self._secuencias and self._secuencias[-1]:
            self.checker.errors.add(
                "código inalcanzable: esta sentencia nunca se ejecuta", ctx)

    # ------------------------------------------------------------------
    # Expresiones
    # ------------------------------------------------------------------

    def exitExpression(self, ctx):
        self.tipo_de[id(ctx)] = self._tipo_de(ctx.assignmentExpr())

    def exitExprNoAssign(self, ctx):
        self.tipo_de[id(ctx)] = self._tipo_de(ctx.conditionalExpr())

    def exitTernaryExpr(self, ctx):
        ramas = ctx.expression()
        if not ramas:                      # sin '?': solo una expresión simple
            self.tipo_de[id(ctx)] = self._tipo_de(ctx.logicalOrExpr())
            return
        self._condicion(ctx.logicalOrExpr(), "ternario")
        a, b = self._tipo_de(ramas[0]), self._tipo_de(ramas[1])
        if ts.is_error(a) or ts.is_error(b):
            self.tipo_de[id(ctx)] = ts.ERROR
        elif ts.assignable(a, b, self.checker.is_subclass):
            self.tipo_de[id(ctx)] = a
        elif ts.assignable(b, a, self.checker.is_subclass):
            self.tipo_de[id(ctx)] = b
        else:
            self.tipo_de[id(ctx)] = self.checker._fail(
                "las ramas de la expresión ternaria deben ser compatibles", ctx)

    def exitLogicalOrExpr(self, ctx):
        self._plegar(ctx, ctx.logicalAndExpr(),
                     self._operadores(ctx, {"||"}), self.checker.logical)

    def exitLogicalAndExpr(self, ctx):
        self._plegar(ctx, ctx.equalityExpr(),
                     self._operadores(ctx, {"&&"}), self.checker.logical)

    def exitEqualityExpr(self, ctx):
        hijos = ctx.relationalExpr()
        ops = self._operadores(ctx, {"==", "!="})
        tipos = [self._tipo_de(h) for h in hijos]
        for i, op in enumerate(ops):
            if hijos[i].getText() == hijos[i + 1].getText():
                self.checker.errors.add(
                    f"comparación sin sentido: '{hijos[i].getText()}' "
                    f"se compara consigo misma", ctx)
            tipos[i + 1] = self.checker.comparison(
                op, tipos[i], tipos[i + 1], ctx)
        self.tipo_de[id(ctx)] = tipos[-1]

    def exitRelationalExpr(self, ctx):
        self._plegar(ctx, ctx.additiveExpr(),
                     self._operadores(ctx, {"<", "<=", ">", ">="}),
                     self.checker.comparison)

    def exitAdditiveExpr(self, ctx):
        self._plegar(ctx, ctx.multiplicativeExpr(),
                     self._operadores(ctx, {"+", "-"}), self.checker.arithmetic)

    def exitMultiplicativeExpr(self, ctx):
        hijos = ctx.unaryExpr()
        ops = self._operadores(ctx, {"*", "/", "%"})
        tipos = [self._tipo_de(h) for h in hijos]
        for i, op in enumerate(ops):
            if op in ("/", "%") and hijos[i + 1].getText() == "0":
                self.checker.errors.add(
                    f"{'división' if op == '/' else 'módulo'} por cero: "
                    f"el divisor es el literal '0'", ctx)
            tipos[i + 1] = self.checker.arithmetic(op, tipos[i], tipos[i + 1], ctx)
        self.tipo_de[id(ctx)] = tipos[-1]

    def exitUnaryExpr(self, ctx):
        primaria = ctx.primaryExpr()
        if primaria is not None:
            self.tipo_de[id(ctx)] = self._tipo_de(primaria)
        else:
            op = ctx.getChild(0).getText()
            self.tipo_de[id(ctx)] = self.checker.unary(
                op, self._tipo_de(ctx.unaryExpr(0)), ctx)

    def exitPrimaryExpr(self, ctx):
        self.tipo_de[id(ctx)] = self._tipo_de(ctx.getChild(0))

    def exitLiteralExpr(self, ctx):
        if ctx.Literal() is not None:
            texto = ctx.Literal().getText()
            self.tipo_de[id(ctx)] = ts.STRING if texto.startswith('"') else ts.INTEGER
        elif ctx.arrayLiteral() is not None:
            self.tipo_de[id(ctx)] = self._tipo_de(ctx.arrayLiteral())
        else:
            texto = ctx.getChild(0).getText()
            self.tipo_de[id(ctx)] = {"null": ts.NULL, "true": ts.BOOLEAN,
                                     "false": ts.BOOLEAN}.get(texto, ts.ERROR)

    def exitArrayLiteral(self, ctx):
        self.tipo_de[id(ctx)] = self.checker.array_literal(
            [self._tipo_de(e) for e in ctx.expression()], ctx)

    def exitIdentifierExpr(self, ctx):
        nombre = ctx.Identifier().getText()
        self._nombres[id(ctx)] = nombre
        self.tipo_de[id(ctx)] = ("id", nombre)

    def exitThisExpr(self, ctx):
        self.tipo_de[id(ctx)] = self.checker.check_this(ctx)

    def exitNewExpr(self, ctx):
        self.tipo_de[id(ctx)] = self.checker.check_new(
            ctx.Identifier().getText(), self._tipos(ctx.arguments()), ctx)

    def exitLeftHandSide(self, ctx):
        atomo = ctx.primaryAtom()
        sufijos = ctx.suffixOp()

        if not sufijos and isinstance(atomo, CompiscriptParser.IdentifierExprContext):
            nombre = self._nombres[id(atomo)]
            self._destino[id(ctx)] = ("id", nombre)
            self.tipo_de[id(ctx)] = ("id", nombre)
            return

        inicio = 0
        if isinstance(atomo, CompiscriptParser.IdentifierExprContext) and \
                isinstance(sufijos[0], CompiscriptParser.CallExprContext):
            tipo = self.checker.check_call(
                self._nombres[id(atomo)], self._tipos(sufijos[0].arguments()), ctx)
            inicio = 1
        else:
            base = self._tipo_de(atomo)
            if isinstance(base, tuple) and len(base) == 2 and base[0] == "id":
                base = self.checker.use_variable(base[1], atomo)
            tipo = base
            if ts.is_error(tipo):
                self.tipo_de[id(ctx)] = tipo
                return

        i = inicio
        while i < len(sufijos):
            suf = sufijos[i]
            if isinstance(suf, CompiscriptParser.PropertyAccessExprContext):
                miembro = suf.Identifier().getText()
                if (i + 1 < len(sufijos) and
                        isinstance(sufijos[i + 1], CompiscriptParser.CallExprContext)):
                    tipo = self.checker.check_member_call(
                        tipo, miembro, self._tipos(sufijos[i + 1].arguments()), ctx)
                    i += 2
                else:
                    if i == len(sufijos) - 1:
                        self._destino[id(ctx)] = ("propiedad", tipo, miembro)
                    tipo = self.checker.check_member_access(tipo, miembro, ctx)
                    i += 1
            elif isinstance(suf, CompiscriptParser.IndexExprContext):
                indice = self._tipo_de(suf.expression())
                if i == len(sufijos) - 1:
                    self._destino[id(ctx)] = ("indice", tipo, indice)
                tipo = self.checker.check_index(tipo, indice, ctx)
                i += 1
            else:                          # llamada sin objeto delante
                break
            if ts.is_error(tipo):
                break
        self.tipo_de[id(ctx)] = tipo

    # ------------------------------------------------------------------
    # Asignaciones
    # ------------------------------------------------------------------

    def exitAssignExpr(self, ctx):
        lhs = ctx.leftHandSide()
        valor = self._tipo_de(ctx.assignmentExpr())
        destino = self._destino.get(id(lhs))
        if destino is None:
            self.checker.errors.add("el destino de la asignación no es asignable", lhs)
        elif destino[0] == "id":
            self.checker.check_assignment(destino[1], valor, lhs)
        elif destino[0] == "indice":
            self.checker.check_index_assign(destino[1], destino[2], valor, lhs)
        else:
            self.checker.check_property_assign(destino[1], destino[2], valor, lhs)
        self.tipo_de[id(ctx)] = valor

    def exitPropertyAssignExpr(self, ctx):
        valor = self._tipo_de(ctx.assignmentExpr())
        self.checker.check_property_assign(
            self._tipo_de(ctx.leftHandSide()), ctx.Identifier().getText(), valor, ctx)
        self.tipo_de[id(ctx)] = valor

    def exitAssignment(self, ctx):
        exprs = ctx.expression()
        if len(exprs) == 1:
            self.checker.check_assignment(
                ctx.Identifier().getText(), self._tipo_de(exprs[0]), ctx)
        else:
            self.checker.check_property_assign(
                self._tipo_de(exprs[0]), ctx.Identifier().getText(),
                self._tipo_de(exprs[1]), ctx)

    # ------------------------------------------------------------------
    # Declaraciones
    # ------------------------------------------------------------------

    def exitVariableDeclaration(self, ctx):
        anotacion = ctx.typeAnnotation()
        inicializador = ctx.initializer()
        self.checker.declare_variable(
            ctx.Identifier().getText(),
            self._tipo_anotacion(anotacion.type_()) if anotacion is not None else None,
            self._tipo_de(inicializador.expression()) if inicializador is not None else None,
            ctx)

    def exitConstantDeclaration(self, ctx):
        anotacion = ctx.typeAnnotation()
        self.checker.declare_constant(
            ctx.Identifier().getText(),
            self._tipo_anotacion(anotacion.type_()) if anotacion is not None else None,
            self._tipo_de(ctx.expression()), ctx)

    def enterFunctionDeclaration(self, ctx):
        params = []
        if ctx.parameters() is not None:
            for p in ctx.parameters().parameter():
                params.append((p.Identifier().getText(),
                               self._tipo_anotacion(p.type_())))
        self.checker.declare_function(
            ctx.Identifier().getText(), params,
            self._tipo_anotacion(ctx.type_()), ctx)
        self.checker.enter_function(self.checker.table.lookup_local(
            ctx.Identifier().getText()), ctx)

    def exitFunctionDeclaration(self, ctx):
        self.checker.exit_function(ctx)

    def enterClassDeclaration(self, ctx):
        ids = ctx.Identifier()
        self.checker.enter_class(
            self.checker.declare_class(ids[0].getText(), ctx,
                                       parent=ids[1].getText() if len(ids) > 1 else None),
            ctx)

    def exitClassDeclaration(self, ctx):
        self.checker.exit_class(ctx)

    # ------------------------------------------------------------------
    # Sentencias
    # ------------------------------------------------------------------

    def exitExpressionStatement(self, ctx):
        self._tipo_de(ctx.expression())

    def exitPrintStatement(self, ctx):
        tipo = self._tipo_de(ctx.expression())
        if tipo == ts.VOID:
            self.checker.errors.add(
                "'print' no puede imprimir una expresión de tipo 'void'", ctx)

    def exitIfStatement(self, ctx):
        self._condicion(ctx.expression(), "if")

    def exitWhileStatement(self, ctx):
        self._condicion(ctx.expression(), "while")
        self.checker.exit_loop()

    def enterWhileStatement(self, ctx):
        self.checker.enter_loop()

    def exitDoWhileStatement(self, ctx):
        self._condicion(ctx.expression(), "do-while")
        self.checker.exit_loop()

    def enterDoWhileStatement(self, ctx):
        self.checker.enter_loop()

    def enterForStatement(self, ctx):
        self.checker.enter_loop()

    def exitForStatement(self, ctx):
        self.checker.exit_loop()
        vistos = 0
        punto_y_coma = 0
        primero = None
        for hijo in ctx.getChildren():
            if getattr(hijo, "getSymbol", None) is not None \
                    and hijo.getSymbol().text == ";":
                punto_y_coma += 1
            elif hasattr(hijo, "getRuleIndex") \
                    and hijo.getRuleIndex() == CompiscriptParser.RULE_expression \
                    and primero is None:
                primero = (hijo, punto_y_coma)
        # La condición es la primera expresión directa del for (el init, cuando
        # es variableDeclaration, ya consumió su ';'). Solo se descarta cuando
        # el init está vacío y la condición también ('for (;; iteracion)',
        # donde van dos ';' antes de la primera expresión).
        if primero is not None and primero[1] <= 1:
            self._condicion(primero[0], "for")

    def enterForeachStatement(self, ctx):
        self.checker.enter_loop()

    def exitForeachStatement(self, ctx):
        self.checker.exit_loop()

    def enterSwitchStatement(self, ctx):
        self.checker.enter_switch(ctx)

    def enterSwitchCase(self, ctx):
        self._secuencias.append(False)

    def exitSwitchCase(self, ctx):
        self._secuencias.pop()

    def exitSwitchStatement(self, ctx):
        sujeto = self._tipo_de(ctx.expression())
        for caso in ctx.switchCase():
            self.checker.check_switch_case(sujeto,
                                           self._tipo_de(caso.expression()), caso,
                                           caso.expression().getText())
        self.checker.exit_switch(ctx)

    def exitReturnStatement(self, ctx):
        expr = ctx.expression()
        self.checker.check_return(self._tipo_de(expr) if expr is not None else None,
                                  ctx)
        self._terminar_secuencia()

    def enterBreakStatement(self, ctx):
        self.checker.check_break(ctx)
        self._terminar_secuencia()

    def enterContinueStatement(self, ctx):
        self.checker.check_continue(ctx)
        self._terminar_secuencia()

    def enterBlock(self, ctx):
        self._secuencias.append(False)
        if self._es_cuerpo_de_funcion(ctx):
            return
        self.checker.table.enter_scope("block")
        padre = ctx.parentCtx
        if isinstance(padre, CompiscriptParser.ForeachStatementContext):
            self.checker.check_foreach(
                padre.Identifier().getText(), self._tipo_de(padre.expression()), ctx)
        elif (isinstance(padre, CompiscriptParser.TryCatchStatementContext) and
                ctx is not padre.block(0)):
            nombre = padre.Identifier().getText()
            self.checker.declare_variable(nombre, ts.STRING, ts.STRING, ctx)

    def exitBlock(self, ctx):
        self._secuencias.pop()
        if not self._es_cuerpo_de_funcion(ctx):
            self.checker.table.exit_scope()