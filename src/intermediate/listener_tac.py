"""
Listener de generación de código intermedio (TAC) de Compiscript.

Recorre el árbol de ANTLR —después del análisis semántico, sobre una
tabla de símbolos completa y con direcciones ya asignadas— y traduce
cada nodo a cuádruplos a través del GeneradorTAC, igual que
SemanticListener traduce a llamadas del SemanticChecker:

    ParseTreeWalker.DEFAULT.walk(ListenerTAC(generador), arbol)

Valores. Cada nodo de expresión deja su operando en `valor_de` al
salir: un literal (tal cual), la dirección de una variable
('fp+16') o el nombre de un temporal ('t1'). El nodo padre los
consume para emitir el cuádruplo de su operación; los temporales
que ya no sirven se liberan en el momento del consumo (un
cuádruplo lee antes de escribir, así que liberar antes de pedir el
temporal del resultado es válido: es el reciclaje de temporales).

Ámbitos. El recorrido entra y sale de los mismos ámbitos que
SemanticListener (función, clase, bloque y `for`), pero SIN mutar la
tabla de símbolos: el listener mantiene su propia pila, consumiendo
los Scope hijos en el mismo orden en que el análisis semántico los
creó (ambos recorridos visitan el árbol en el mismo orden). Así,
`_buscar` resuelve el símbolo correcto en el momento del uso —por
ejemplo, la local que sombrea a una global— sin duplicar ámbitos en
el árbol que muestra el IDE.

Closures. Una variable que vive en el marco de OTRA función (una
capturada del entorno) se referencia por su nombre, no por su
dirección: su `fp+N` pertenece al marco de la función contenedora y
alcanzarla es trabajo de la generación de código objeto, que recorre
el enlace estático (DISENO_TAC.md §7).

Miembros de clase. Una declaración de variable o constante cuyo
ámbito directo es la clase es parte del layout del objeto, no código
ejecutable: no emite nada (la dirección `obj+N` la asigna memoria.py).

Ganchos pendientes. Las construcciones que traducen las demás etapas
(control de flujo: Etapa 2; llamadas: Etapa 3; clases, `new`,
`this`, miembros e índices: Persona 3) emiten un comentario
'pendiente' y un operando provisorio, de modo que el recorrido
sobrevive a programas que las usan y el IDE muestra exactamente qué
falta por traducir.
"""

from __future__ import annotations

import os
import sys

# El proyecto usa imports flat (igual que SemanticListener y los
# tests): se añaden las carpetas a sys.path para importar sin
# prefijos.
_AQUI = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.dirname(_AQUI)
for _paquete in ("parser", "semantic"):
    _ruta = os.path.join(_SRC, _paquete)
    if _ruta not in sys.path:
        sys.path.insert(0, _ruta)

from generated.CompiscriptParser import CompiscriptParser
from generated.CompiscriptListener import CompiscriptListener

from tac import NEGATIVO, NEGACION


class ListenerTAC(CompiscriptListener):
    """Traduce el árbol sintáctico a una lista de cuádruplos."""

    def __init__(self, gen):
        self.gen = gen
        self.valor_de: dict[int, str] = {}    # id(nodo) -> operando
        # Espejo del recorrido semántico: la pila de ámbitos por la
        # que va el walker, sin tocar la tabla de símbolos.
        self._ambitos = [gen.tabla.global_scope]
        self._consumidos: set[int] = set()    # ámbitos hijos ya usados

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    def _entrar_ambito(self, kind: str, nombre: str | None = None):
        """Empuja el Scope que el análisis semántico creó para este
        nodo. Como ambos listeners recorren el árbol en el mismo
        orden, el ámbito que corresponde a este nodo es el primer
        hijo sin consumir del ámbito actual con ese tipo y nombre."""
        actual = self._ambitos[-1]
        for hijo in actual.children:
            if (hijo.kind == kind and hijo.name == nombre
                    and id(hijo) not in self._consumidos):
                self._consumidos.add(id(hijo))
                self._ambitos.append(hijo)
                return hijo
        return None

    def _salir_ambito(self) -> None:
        self._ambitos.pop()

    def _buscar(self, nombre: str):
        """(símbolo, ámbito donde se encontró), o (None, None)."""
        for ambito in reversed(self._ambitos):
            simbolo = ambito.resolve_local(nombre)
            if simbolo is not None:
                return simbolo, ambito
        return None, None

    def _destino(self, nombre: str) -> str:
        """Operando donde vive una variable.

        Es su dirección ('global+N', 'fp+N', 'obj+N'), salvo que
        viva en el marco de otra función: entonces es su nombre, y
        el código objeto la alcanza por el enlace estático (§7)."""
        simbolo, ambito = self._buscar(nombre)
        if simbolo is None or not simbolo.direccion:
            return nombre                     # función o sin resolver
        if (simbolo.direccion.startswith("fp+")
                and not self._en_marco_actual(ambito)):
            return nombre                     # capturada de un cierre
        return simbolo.direccion

    def _en_marco_actual(self, ambito) -> bool:
        """¿`ambito` es el ámbito de la función abierta o alguno de
        sus bloques? (Los bloques no crean marco: sus variables
        viven en el marco de la función que los contiene.)"""
        for i in range(len(self._ambitos) - 1, -1, -1):
            if self._ambitos[i].kind == "function":
                return self._ambitos.index(ambito) >= i
        return True        # programa principal: un solo área

    def _valor(self, ctx) -> str:
        """Operando de un nodo de expresión ya traducido."""
        return self.valor_de.get(id(ctx), ctx.getText())

    def _operadores(self, ctx, ops: set) -> list[str]:
        return [h.getText() for h in ctx.getChildren()
                if getattr(h, "getSymbol", None) is not None
                and h.getSymbol().text in ops]

    def _pendiente(self, que: str) -> None:
        """Marca una construcción que traducirá otra etapa."""
        self.gen.programa.emitir_comentario(f"pendiente: {que}")

    def _gancho(self, que: str, ctx) -> str:
        """Construcción pendiente: comentario y operando provisorio,
        para que el recorrido sobreviva a programas que la usan."""
        self._pendiente(que)
        return f"/*{que}*/ {ctx.getText()}"

    def _plegar(self, ctx, hijos, ops: set) -> None:
        """Traduce una cadena de operadores binarios, de izquierda a
        derecha, reciclando los temporales de los operandos."""
        valores = [self._valor(h) for h in hijos]
        for i, operador in enumerate(self._operadores(ctx, ops)):
            izq, der = valores[i], valores[i + 1]
            destino = self.gen.temporal_para(izq, der)
            self.gen.programa.emitir_binaria(operador, izq, der, destino)
            valores[i + 1] = destino
        self.valor_de[id(ctx)] = valores[-1]

    # ------------------------------------------------------------------
    # Expresiones
    # ------------------------------------------------------------------

    def exitExpression(self, ctx):
        self.valor_de[id(ctx)] = self._valor(ctx.assignmentExpr())

    def exitExprNoAssign(self, ctx):
        self.valor_de[id(ctx)] = self._valor(ctx.conditionalExpr())

    def exitTernaryExpr(self, ctx):
        ramas = ctx.expression()
        if not ramas:                     # sin '?': expresión simple
            self.valor_de[id(ctx)] = self._valor(ctx.logicalOrExpr())
            return
        condicion = self._valor(ctx.logicalOrExpr())
        self.gen.liberar(condicion)       # muere en el ifFalse
        verdadera = self._valor(ramas[0])
        falsa = self._valor(ramas[1])
        otro = self.gen.nueva_etiqueta("ternario_sino")
        fin = self.gen.nueva_etiqueta("ternario_fin")
        destino = self.gen.nuevo_temporal()
        programa = self.gen.programa
        programa.emitir_salto_si_falso(condicion, otro)
        programa.emitir_asignacion(destino, verdadera)
        self.gen.liberar(verdadera)
        programa.emitir_salto(fin)
        programa.emitir_etiqueta(otro)
        programa.emitir_asignacion(destino, falsa)
        self.gen.liberar(falsa)
        programa.emitir_etiqueta(fin)
        self.valor_de[id(ctx)] = destino

    def exitLiteralExpr(self, ctx):
        if ctx.Literal() is not None:
            self.valor_de[id(ctx)] = ctx.Literal().getText()
        elif ctx.arrayLiteral() is not None:
            self.valor_de[id(ctx)] = self._valor(ctx.arrayLiteral())
        else:                      # true | false | null
            self.valor_de[id(ctx)] = ctx.getChild(0).getText()

    def exitArrayLiteral(self, ctx):
        self.valor_de[id(ctx)] = self._gancho("arreglo literal (Persona 3)",
                                              ctx)

    def exitPrimaryExpr(self, ctx):
        hijo = ctx.getChild(0)
        if getattr(hijo, "getSymbol", None) is not None:
            # '(' expression ')': el paréntesis es el primer hijo.
            hijo = ctx.getChild(1)
        self.valor_de[id(ctx)] = self._valor(hijo)

    def exitUnaryExpr(self, ctx):
        primaria = ctx.primaryExpr()
        if primaria is not None:
            self.valor_de[id(ctx)] = self._valor(primaria)
            return
        operador = ctx.getChild(0).getText()
        operando = self._valor(ctx.unaryExpr())
        op = NEGATIVO if operador == "-" else NEGACION
        destino = self.gen.temporal_para(operando)
        self.gen.programa.emitir_unaria(op, operando, destino)
        self.valor_de[id(ctx)] = destino

    def exitLogicalOrExpr(self, ctx):
        self._plegar(ctx, ctx.logicalAndExpr(), {"||"})

    def exitLogicalAndExpr(self, ctx):
        self._plegar(ctx, ctx.equalityExpr(), {"&&"})

    def exitEqualityExpr(self, ctx):
        self._plegar(ctx, ctx.relationalExpr(), {"==", "!="})

    def exitRelationalExpr(self, ctx):
        self._plegar(ctx, ctx.additiveExpr(), {"<", "<=", ">", ">="})

    def exitAdditiveExpr(self, ctx):
        self._plegar(ctx, ctx.multiplicativeExpr(), {"+", "-"})

    def exitMultiplicativeExpr(self, ctx):
        self._plegar(ctx, ctx.unaryExpr(), {"*", "/", "%"})

    def exitIdentifierExpr(self, ctx):
        self.valor_de[id(ctx)] = self._destino(ctx.Identifier().getText())

    def exitNewExpr(self, ctx):
        self.valor_de[id(ctx)] = self._gancho("new (Persona 3)", ctx)

    def exitThisExpr(self, ctx):
        self.valor_de[id(ctx)] = self._gancho("this (Persona 3)", ctx)

    def exitLeftHandSide(self, ctx):
        atomo = ctx.primaryAtom()
        sufijos = ctx.suffixOp()
        if not sufijos and isinstance(
                atomo, CompiscriptParser.IdentifierExprContext):
            # Variable simple: su operando ya lo dio exitIdentifierExpr.
            self.valor_de[id(ctx)] = self._valor(atomo)
        elif (isinstance(atomo, CompiscriptParser.IdentifierExprContext)
                and sufijos
                and isinstance(sufijos[0], CompiscriptParser.CallExprContext)):
            self.valor_de[id(ctx)] = self._gancho("llamada (Etapa 3)", ctx)
        else:
            self.valor_de[id(ctx)] = self._gancho(
                "acceso a miembro o índice (Persona 3)", ctx)

    def exitAssignExpr(self, ctx):
        lhs = ctx.leftHandSide()
        valor = self._valor(ctx.assignmentExpr())
        atomo = lhs.primaryAtom()
        if not lhs.suffixOp() and isinstance(
                atomo, CompiscriptParser.IdentifierExprContext):
            destino = self._destino(atomo.Identifier().getText())
            self.gen.programa.emitir_asignacion(destino, valor)
        else:
            # Asignación a propiedad o índice: Persona 3.
            self._pendiente(f"asignación a {lhs.getText()} (Persona 3)")
        # El valor lo libera quien consuma esta expresión (la
        # sentencia de asignación o la expresión padre).
        self.valor_de[id(ctx)] = valor

    def exitPropertyAssignExpr(self, ctx):
        valor = self._valor(ctx.assignmentExpr())
        self._pendiente("asignación a propiedad (Persona 3)")
        self.gen.liberar(valor)
        self.valor_de[id(ctx)] = valor

    # ------------------------------------------------------------------
    # Declaraciones y sentencias
    # ------------------------------------------------------------------

    def _es_miembro_de_clase(self) -> bool:
        """El ámbito directo es una clase: la declaración es parte
        del layout del objeto, no código ejecutable."""
        return self._ambitos[-1].kind == "class"

    def exitVariableDeclaration(self, ctx):
        if self._es_miembro_de_clase():
            return
        inicializador = ctx.initializer()
        if inicializador is None:
            return
        valor = self._valor(inicializador.expression())
        self.gen.programa.emitir_asignacion(
            self._destino(ctx.Identifier().getText()), valor)
        self.gen.liberar(valor)

    def exitConstantDeclaration(self, ctx):
        if self._es_miembro_de_clase():
            return
        valor = self._valor(ctx.expression())
        self.gen.programa.emitir_asignacion(
            self._destino(ctx.Identifier().getText()), valor)
        self.gen.liberar(valor)

    def exitAssignment(self, ctx):
        exprs = ctx.expression()
        if len(exprs) == 1:
            # Identifier '=' expression ';'
            valor = self._valor(exprs[0])
            self.gen.programa.emitir_asignacion(
                self._destino(ctx.Identifier().getText()), valor)
            self.gen.liberar(valor)
        else:
            # expression '.' Identifier '=' expression ';': Persona 3.
            self._pendiente("asignación a propiedad (Persona 3)")
            self.gen.liberar(self._valor(exprs[1]))

    def exitExpressionStatement(self, ctx):
        # La expresión ya emitió su código; si quedó un temporal
        # suelto (una expresión sin efecto), se libera.
        self.gen.liberar(self._valor(ctx.expression()))

    def exitPrintStatement(self, ctx):
        valor = self._valor(ctx.expression())
        self.gen.programa.emitir_print(valor)
        self.gen.liberar(valor)

    def exitReturnStatement(self, ctx):
        expr = ctx.expression()
        if expr is None:
            self.gen.programa.emitir_retorno()
            return
        valor = self._valor(expr)
        self.gen.programa.emitir_retorno(valor)
        self.gen.liberar(valor)

    # ------------------------------------------------------------------
    # Ámbitos y funciones (espejo del recorrido semántico)
    # ------------------------------------------------------------------

    def _es_cuerpo_de_funcion(self, ctx) -> bool:
        return isinstance(ctx.parentCtx,
                          CompiscriptParser.FunctionDeclarationContext)

    def enterFunctionDeclaration(self, ctx):
        nombre = ctx.Identifier().getText()
        self._entrar_ambito("function", nombre)
        self.gen.entrar_funcion(nombre)

    def exitFunctionDeclaration(self, ctx):
        self.gen.salir_funcion()
        self._salir_ambito()

    def enterClassDeclaration(self, ctx):
        nombre = ctx.Identifier(0).getText()
        self._entrar_ambito("class", nombre)
        self.gen.entrar_clase(nombre)

    def exitClassDeclaration(self, ctx):
        self.gen.salir_clase()
        self._salir_ambito()

    def enterBlock(self, ctx):
        if self._es_cuerpo_de_funcion(ctx):
            return        # el ámbito de la función ya está abierto
        self._entrar_ambito("block")

    def exitBlock(self, ctx):
        if self._es_cuerpo_de_funcion(ctx):
            return
        self._salir_ambito()

    def enterForStatement(self, ctx):
        # El inicializador del 'for' queda fuera del bloque: el ciclo
        # abre su propio ámbito (la variable del init vive en la
        # condición, la iteración y el cuerpo, pero no después).
        self._entrar_ambito("block")
        self._pendiente("for (Etapa 2)")

    def exitForStatement(self, ctx):
        self._salir_ambito()

    # ------------------------------------------------------------------
    # Construcciones de la Etapa 2 (control de flujo): por ahora solo
    # marcan lo pendiente; sus expresiones internas sí se traducen.
    # ------------------------------------------------------------------

    def enterIfStatement(self, ctx):
        self._pendiente("if (Etapa 2)")

    def enterWhileStatement(self, ctx):
        self._pendiente("while (Etapa 2)")

    def enterDoWhileStatement(self, ctx):
        self._pendiente("do-while (Etapa 2)")

    def enterForeachStatement(self, ctx):
        self._pendiente("foreach (Etapa 2)")

    def enterSwitchStatement(self, ctx):
        self._pendiente("switch (Etapa 2)")

    def enterTryCatchStatement(self, ctx):
        self._pendiente("try/catch (Etapa 2)")

    def enterBreakStatement(self, ctx):
        self._pendiente("break (Etapa 2)")

    def enterContinueStatement(self, ctx):
        self._pendiente("continue (Etapa 2)")
