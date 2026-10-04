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

Ganchos pendientes. Las construcciones que traducen las otras
etapas (llamadas: Etapa 3; clases, `new`, `this`, miembros e
índices: Persona 3) emiten un comentario 'pendiente' y un
operando provisorio, de modo que el recorrido sobrevive a
programas que las usan y el IDE muestra exactamente qué falta
por traducir.

Control de flujo. El walker va de abajo hacia arriba, pero cada
constructo salta en los puntos donde su sub-árbol ya está
traducido: la condición en el 'exit' de su expresión (o en el
'entrar' del bloque, para el 'if' y el 'while'), el cuerpo en
el 'entrar'/'salir' de su bloque, y la etiqueta final en el
'salir' del constructo. El 'for' usa el mismo truco para el
inicializador (su etiqueta de inicio se emite al traducirlo) y
para el paso (su etiqueta se emite al ENTRAR la expresión, antes
de su código). Cada constructo apila un marco con sus etiquetas;
'break' y 'continue' consultan la pila de ciclos del GeneradorTAC.
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
        # Marcos de los constructos abiertos (cada uno apila las
        # etiquetas que traducen sus bloques y sus saltos).
        self._ifs: list[dict] = []            # if / else
        self._ciclos: list[dict] = []         # while, do-while, for, foreach
        self._switchs: list[dict] = []        # switch
        self._trys: list[dict] = []           # try / catch

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

    def _clasificar_expresiones_de_for(self, for_ctx) -> dict:
        """En el 'for', la condición es la primera expresión directa
        y el paso, la segunda. Si solo hay una, es el paso cuando
        tiene dos ';' directos antes ('for (init; ; paso)' o
        'for (;; paso)') y la condición si no (0 o 1: el ';'
        del inicializador vive dentro de su propio contexto)."""
        encontradas: dict[str, object] = {}
        punto_y_coma = 0
        expresiones: list[tuple[int, object]] = []
        for hijo in for_ctx.getChildren():
            if (getattr(hijo, "getSymbol", None) is not None
                    and hijo.getSymbol().text == ";"):
                punto_y_coma += 1
            elif (hasattr(hijo, "getRuleIndex")
                    and hijo.getRuleIndex()
                    == CompiscriptParser.RULE_expression):
                expresiones.append((punto_y_coma, hijo))
        if len(expresiones) >= 2:
            encontradas["condicion"] = expresiones[0][1]
            encontradas["paso"] = expresiones[1][1]
        elif len(expresiones) == 1:
            cuenta, expr = expresiones[0]
            if cuenta >= 2:
                encontradas["paso"] = expr
            else:
                encontradas["condicion"] = expr
        return encontradas

    def _es_condicion_de_for(self, ctx) -> bool:
        padre = ctx.parentCtx
        if not isinstance(padre, CompiscriptParser.ForStatementContext):
            return False
        return (self._clasificar_expresiones_de_for(padre)
                .get("condicion") is ctx)

    def _es_paso_de_for(self, ctx) -> bool:
        padre = ctx.parentCtx
        if not isinstance(padre, CompiscriptParser.ForStatementContext):
            return False
        return (self._clasificar_expresiones_de_for(padre)
                .get("paso") is ctx)

    def _es_condicion_de_dowhile(self, ctx) -> bool:
        return isinstance(ctx.parentCtx,
                          CompiscriptParser.DoWhileStatementContext)

    def _es_sujeto_de_switch(self, ctx) -> bool:
        return isinstance(ctx.parentCtx,
                          CompiscriptParser.SwitchStatementContext)

    def _es_valor_de_case(self, ctx) -> bool:
        return isinstance(ctx.parentCtx,
                          CompiscriptParser.SwitchCaseContext)

    def _es_iterable_de_foreach(self, ctx) -> bool:
        return isinstance(ctx.parentCtx,
                          CompiscriptParser.ForeachStatementContext)

    # ------------------------------------------------------------------
    # Expresiones
    # ------------------------------------------------------------------

    def enterExpression(self, ctx):
        if self._es_paso_de_for(ctx):
            # El paso se traduce DESPUÉS del cuerpo: esta etiqueta
            # marca dónde empieza (y adónde salta 'continue').
            self.gen.programa.emitir_etiqueta(
                self._ciclos[-1]["paso"])
        elif self._es_condicion_de_dowhile(ctx):
            # La condición del do-while se traduce al final: aquí
            # empieza, y es adónde salta 'continue'.
            self.gen.programa.emitir_etiqueta(
                self._ciclos[-1]["cond"])

    def exitExpression(self, ctx):
        self.valor_de[id(ctx)] = self._valor(ctx.assignmentExpr())
        if self._es_condicion_de_for(ctx):
            # El 'ifFalse' va justo después de la condición.
            marco = self._ciclos[-1]
            condicion = self.valor_de[id(ctx)]
            self.gen.liberar(condicion)
            self.gen.programa.emitir_salto_si_falso(
                condicion, marco["fin"])
        elif self._es_paso_de_for(ctx):
            # El paso ya está traducido: vuelve al inicio y marca
            # dónde empieza el cuerpo. Su valor ya está asignado
            # (es una asignación), así que el temporal sobra.
            marco = self._ciclos[-1]
            self.gen.liberar(self.valor_de[id(ctx)])
            programa = self.gen.programa
            programa.emitir_salto(marco["inicio"])
            programa.emitir_etiqueta(marco["cuerpo"])
        elif self._es_sujeto_de_switch(ctx):
            # El sujeto se compara con cada caso: vive todo el
            # switch y se libera en exitSwitchStatement.
            self._switchs[-1]["sujeto"] = self.valor_de[id(ctx)]
        elif self._es_valor_de_case(ctx):
            # Cadena de comparaciones: el caso se evalúa solo si
            # los anteriores no cuadraron (§2 del doc).
            marco = self._switchs[-1]
            valor = self._valor(ctx)
            condicion = self.gen.nuevo_temporal()
            programa = self.gen.programa
            programa.emitir_binaria("==", marco["sujeto"], valor,
                                    condicion)
            self.gen.liberar(valor)
            programa.emitir_salto_si_falso(condicion, marco["no"][-1])
            self.gen.liberar(condicion)
        elif self._es_iterable_de_foreach(ctx):
            # Condición del ciclo desarmado: índice < length(arreglo).
            # Ni el índice ni el arreglo se liberan: viven todo
            # el ciclo (el índice se recicla en el incremento).
            marco = self._ciclos[-1]
            arreglo = self._valor(ctx)
            marco["arreglo"] = arreglo
            programa = self.gen.programa
            tamano = self.gen.nuevo_temporal()
            programa.emitir_longitud(arreglo, tamano)
            condicion = self.gen.nuevo_temporal()
            programa.emitir_binaria("<", marco["indice"], tamano,
                                    condicion)
            self.gen.liberar(tamano)
            programa.emitir_salto_si_falso(condicion, marco["fin"])
            self.gen.liberar(condicion)

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

    def _emitir_inicio_de_for(self, ctx) -> None:
        """El inicializador del 'for' ya está traducido: empieza la
        etiqueta de inicio del ciclo (va DESPUÉS del inicializador
        y ANTES de la condición)."""
        padre = ctx.parentCtx
        if not isinstance(padre, CompiscriptParser.ForStatementContext):
            return
        marco = self._ciclos[-1]
        if marco["inicio_pendiente"]:
            marco["inicio_pendiente"] = False
            self.gen.programa.emitir_etiqueta(marco["inicio"])

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
        self._emitir_inicio_de_for(ctx)

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
        self._emitir_inicio_de_for(ctx)

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
        padre = ctx.parentCtx
        if isinstance(padre, CompiscriptParser.IfStatementContext):
            if ctx is padre.block(0):
                # Bloque 'then': si la condición es falsa, salta
                # al 'else' (o al fin, si no lo hay).
                marco = self._ifs[-1]
                condicion = self._valor(padre.expression())
                self.gen.liberar(condicion)
                self.gen.programa.emitir_salto_si_falso(
                    condicion, marco["otro"] or marco["fin"])
            else:
                # El bloque 'else' empieza donde aterrizó el
                # salto del 'ifFalse'.
                self.gen.programa.emitir_etiqueta(
                    self._ifs[-1]["otro"])
        elif isinstance(padre, CompiscriptParser.WhileStatementContext):
            # El 'while': si la condición es falsa, el cuerpo
            # no se ejecuta.
            marco = self._ciclos[-1]
            condicion = self._valor(padre.expression())
            self.gen.liberar(condicion)
            self.gen.programa.emitir_salto_si_falso(
                condicion, marco["fin"])
        elif isinstance(padre, CompiscriptParser.TryCatchStatementContext):
            if ctx is padre.block(1):
                # El 'catch' empieza donde aterrizan las
                # excepciones de tiempo de ejecución.
                self.gen.programa.emitir_etiqueta(
                    self._trys[-1]["catch"])
        elif isinstance(padre, CompiscriptParser.ForeachStatementContext):
            # Elemento del ciclo: variable = arreglo[indice].
            marco = self._ciclos[-1]
            self.gen.programa.emitir_lectura_indice(
                marco["arreglo"], marco["indice"],
                self._destino(marco["variable"]))

    def exitBlock(self, ctx):
        if self._es_cuerpo_de_funcion(ctx):
            return
        padre = ctx.parentCtx
        programa = self.gen.programa
        if isinstance(padre, CompiscriptParser.IfStatementContext):
            if (ctx is padre.block(0) and len(padre.block()) > 1):
                # Fin del 'then': con 'else', salta al fin para
                # no caer en el bloque contrario.
                programa.emitir_salto(self._ifs[-1]["fin"])
        elif isinstance(padre, CompiscriptParser.WhileStatementContext):
            programa.emitir_salto(self._ciclos[-1]["inicio"])
        elif isinstance(padre, CompiscriptParser.ForStatementContext):
            # Vuelve al paso (o a la condición, si no hay).
            programa.emitir_salto(self._ciclos[-1]["volver"])
        elif isinstance(padre, CompiscriptParser.ForeachStatementContext):
            # Fin del cuerpo: incremento y vuelta al inicio.
            marco = self._ciclos[-1]
            programa.emitir_etiqueta(marco["paso"])
            # índice = índice + 1 (recicla el propio índice).
            incremento = self.gen.temporal_para(marco["indice"], "1")
            programa.emitir_binaria("+", marco["indice"], "1",
                                    incremento)
            marco["indice"] = incremento
            programa.emitir_salto(marco["inicio"])
        elif isinstance(padre, CompiscriptParser.TryCatchStatementContext):
            if ctx is padre.block(0):
                # Fin del 'try': el flujo normal salta por
                # encima del 'catch'.
                programa.emitir_salto(self._trys[-1]["fin"])
        self._salir_ambito()

    def enterForStatement(self, ctx):
        # El inicializador queda fuera del bloque: el ciclo abre
        # su propio ámbito (la variable del init vive en la
        # condición, la iteración y el cuerpo, pero no después).
        self._entrar_ambito("block")
        inicio = self.gen.nueva_etiqueta("for_inicio")
        fin = self.gen.nueva_etiqueta("for_fin")
        paso = self.gen.nueva_etiqueta("for_paso")
        cuerpo = self.gen.nueva_etiqueta("for_cuerpo")
        tiene_paso = (self._clasificar_expresiones_de_for(ctx)
                      .get("paso") is not None)
        # Sin paso, 'continue' y el final del cuerpo vuelven
        # directo a la condición.
        volver = paso if tiene_paso else inicio
        self._ciclos.append({
            "inicio": inicio, "fin": fin, "paso": paso,
            "cuerpo": cuerpo, "volver": volver,
            # Cuando hay inicializador, la etiqueta de inicio se
            # emite al terminar de traducirlo (va después de él).
            "inicio_pendiente": (ctx.variableDeclaration() is not None
                                 or ctx.assignment() is not None),
        })
        if not self._ciclos[-1]["inicio_pendiente"]:
            self.gen.programa.emitir_etiqueta(inicio)
        self.gen.entrar_ciclo(volver, fin)

    def exitForStatement(self, ctx):
        marco = self._ciclos.pop()
        self.gen.programa.emitir_etiqueta(marco["fin"])
        self.gen.salir_ciclo()
        self._salir_ambito()

    # ------------------------------------------------------------------
    # Control de flujo
    # ------------------------------------------------------------------

    def enterIfStatement(self, ctx):
        self._ifs.append({
            # Solo hay etiqueta de 'else' cuando el bloque existe.
            "otro": (self.gen.nueva_etiqueta("if_else")
                     if len(ctx.block()) > 1 else None),
            "fin": self.gen.nueva_etiqueta("if_fin"),
        })

    def exitIfStatement(self, ctx):
        marco = self._ifs.pop()
        self.gen.programa.emitir_etiqueta(marco["fin"])

    def enterWhileStatement(self, ctx):
        inicio = self.gen.nueva_etiqueta("while_inicio")
        fin = self.gen.nueva_etiqueta("while_fin")
        self._ciclos.append({"inicio": inicio, "fin": fin})
        self.gen.programa.emitir_etiqueta(inicio)
        self.gen.entrar_ciclo(inicio, fin)

    def exitWhileStatement(self, ctx):
        marco = self._ciclos.pop()
        self.gen.programa.emitir_etiqueta(marco["fin"])
        self.gen.salir_ciclo()

    def enterDoWhileStatement(self, ctx):
        inicio = self.gen.nueva_etiqueta("dowhile_inicio")
        fin = self.gen.nueva_etiqueta("dowhile_fin")
        cond = self.gen.nueva_etiqueta("dowhile_cond")
        self._ciclos.append({"inicio": inicio, "fin": fin, "cond": cond})
        self.gen.programa.emitir_etiqueta(inicio)
        # 'continue' salta a la condición, que se traduce al
        # final (su etiqueta se emite en enterExpression).
        self.gen.entrar_ciclo(cond, fin)

    def exitDoWhileStatement(self, ctx):
        marco = self._ciclos.pop()
        condicion = self._valor(ctx.expression())
        self.gen.liberar(condicion)
        # El salto de regreso es un 'if': el cuerpo se ejecuta
        # al menos una vez.
        self.gen.programa.emitir_salto_si(condicion, marco["inicio"])
        self.gen.programa.emitir_etiqueta(marco["fin"])
        self.gen.salir_ciclo()

    def enterForeachStatement(self, ctx):
        # Se desarma en un ciclo indexado (§2 del doc): el índice
        # es un temporal que vive todo el ciclo.
        inicio = self.gen.nueva_etiqueta("foreach_inicio")
        fin = self.gen.nueva_etiqueta("foreach_fin")
        paso = self.gen.nueva_etiqueta("foreach_paso")
        self._ciclos.append({
            "inicio": inicio, "fin": fin, "paso": paso,
            "indice": self.gen.nuevo_temporal(),
            "variable": ctx.Identifier().getText(),
            "arreglo": None,
        })
        marco = self._ciclos[-1]
        programa = self.gen.programa
        programa.emitir_asignacion(marco["indice"], "0")
        programa.emitir_etiqueta(inicio)
        # 'continue' salta al incremento; 'break', al fin.
        self.gen.entrar_ciclo(paso, fin)

    def exitForeachStatement(self, ctx):
        marco = self._ciclos.pop()
        self.gen.programa.emitir_etiqueta(marco["fin"])
        self.gen.liberar(marco["indice"])
        self.gen.liberar(marco["arreglo"])
        self.gen.salir_ciclo()

    def enterSwitchStatement(self, ctx):
        self._switchs.append({
            "sujeto": None,
            "fin": self.gen.nueva_etiqueta("switch_fin"),
            "no": [],       # etiquetas 'no cuadró' de los casos
        })

    def exitSwitchStatement(self, ctx):
        marco = self._switchs.pop()
        self.gen.programa.emitir_etiqueta(marco["fin"])
        self.gen.liberar(marco["sujeto"])

    def enterSwitchCase(self, ctx):
        # Etiqueta a la que salta la cadena cuando este caso
        # no cuadra.
        self._switchs[-1]["no"].append(
            self.gen.nueva_etiqueta("case_no"))

    def exitSwitchCase(self, ctx):
        # Fin del cuerpo del caso: salta al fin del switch y
        # marca dónde continúa la cadena de comparaciones.
        marco = self._switchs[-1]
        programa = self.gen.programa
        programa.emitir_salto(marco["fin"])
        programa.emitir_etiqueta(marco["no"].pop())

    def enterTryCatchStatement(self, ctx):
        self._trys.append({
            "catch": self.gen.nueva_etiqueta("catch"),
            "fin": self.gen.nueva_etiqueta("try_fin"),
        })

    def exitTryCatchStatement(self, ctx):
        marco = self._trys.pop()
        self.gen.programa.emitir_etiqueta(marco["fin"])

    def exitBreakStatement(self, ctx):
        self.gen.programa.emitir_salto(self.gen.etiqueta_salir())

    def exitContinueStatement(self, ctx):
        self.gen.programa.emitir_salto(self.gen.etiqueta_continuar())
