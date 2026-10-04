"""
Listener de generación de código intermedio (TAC) de Compiscript.

Recorre el árbol de ANTLR —después del análisis semántico, sobre
una tabla de símbolos completa y con direcciones ya asignadas— y
traduce cada nodo a cuádruplos a través del GeneradorTAC, igual
que SemanticListener traduce a llamadas del SemanticChecker:

    ParseTreeWalker.DEFAULT.walk(ListenerTAC(generador), arbol)

Cada nodo de expresión deja su operando en `valor_de` al salir (un
literal tal cual, la dirección de una variable o el nombre de un
temporal); el nodo padre lo consume para emitir su cuádruplo, y
los temporales que mueren se liberan en el consumo (reciclaje de
temporales). Los ámbitos se espejan sin mutar la tabla, y las
construcciones que aún no se traducen emiten un comentario
'pendiente' con un operando provisorio para que el recorrido
sobreviva a programas que las usan. Los esquemas de traducción
están en docs/DISENO_TAC.md.
"""

from __future__ import annotations

import os
import sys

# Imports flat, igual que SemanticListener y los tests.
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
        # Destinos de asignación ya resueltos: id(leftHandSide) ->
        # ("indice" | "campo", base, índice o nombre del campo). Los llena
        # exitLeftHandSide y los consume exitAssignExpr, que emite la
        # escritura.
        self._lvalor: dict[int, tuple[str, str, str]] = {}
        # Atributos con inicializador. Su código no puede quedar suelto en el
        # cuerpo de la clase (no hay objeto todavía): se extrae y se junta en
        # una función 'Clase.__atributos' que 'new' llama sobre cada objeto.
        self._clases_con_init: set[str] = set()   # se llena en enterProgram
        self._inits: dict[str, list] = {}         # clase -> [(campo, valor, código)]
        self._inicio_init = 0

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    def _entrar_ambito(self, kind: str, nombre: str | None = None):
        """Empuja el Scope que el análisis semántico creó para
        este nodo (primer hijo sin consumir del ámbito actual
        con ese tipo y nombre)."""
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

    def _nombre_de_funcion(self, simbolo) -> str:
        """Nombre cualificado de una función, según el ámbito que
        la declaró ('contador.interno'). No vale el contexto del
        sitio de llamada: desde el cuerpo de 'factorial', la
        recursiva sigue siendo 'factorial'."""
        for nivel in range(len(self._ambitos) - 1, -1, -1):
            if (self._ambitos[nivel].resolve_local(simbolo.name)
                    is simbolo):
                ruta = [a.name for a in self._ambitos[:nivel + 1]
                        if a.kind in ("function", "class")]
                return ".".join(ruta + [simbolo.name])
        return simbolo.name

    def _destino(self, nombre: str) -> str:
        """Operando donde vive una variable: su dirección, salvo
        que sea una función o una capturada de un cierre (entonces
        su nombre; el código objeto la alcanza por el enlace
        estático, §7 del doc)."""
        simbolo, ambito = self._buscar(nombre)
        if simbolo is None or not simbolo.direccion:
            return nombre                     # función o sin resolver
        if (simbolo.direccion.startswith("fp+")
                and not self._en_marco_actual(ambito)):
            return nombre                     # capturada de un cierre
        return simbolo.direccion

    def _en_marco_actual(self, ambito) -> bool:
        """¿`ambito` es el ámbito de la función abierta o
        uno de sus bloques? (Los bloques no crean marco.)"""
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
        """Marca una construcción aún no traducida."""
        self.gen.programa.emitir_comentario(f"pendiente: {que}")

    def _gancho(self, que: str, ctx) -> str:
        """Construcción pendiente: comentario y operando
        provisorio, para que el recorrido sobreviva."""
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
        """En el 'for', la condición es la primera expresión
        directa y el paso, la segunda. Si hay una sola, es
        el paso cuando tiene dos ';' directos antes (el ';'
        del inicializador vive dentro de su contexto)."""
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

    def enterProgram(self, ctx):
        self._escanear_clases(ctx)

    def _escanear_clases(self, nodo) -> None:
        """Marca las clases con atributos inicializados ANTES de recorrerlas:
        un 'new' puede aparecer en el código antes que la clase."""
        if isinstance(nodo, CompiscriptParser.ClassDeclarationContext):
            for miembro in nodo.classMember():
                variable = miembro.variableDeclaration()
                if (miembro.constantDeclaration() is not None
                        or (variable is not None
                            and variable.initializer() is not None)):
                    self._clases_con_init.add(nodo.Identifier(0).getText())
        for i in range(nodo.getChildCount()):
            self._escanear_clases(nodo.getChild(i))

    def enterExpression(self, ctx):
        if self._es_paso_de_for(ctx):
            # En el árbol el paso viene ANTES del cuerpo, pero se ejecuta
            # después: el flujo normal (condición verdadera, o sin
            # condición) salta el paso hasta el cuerpo, y el paso queda
            # como destino de 'continue' y del fin del cuerpo.
            marco = self._ciclos[-1]
            self.gen.programa.emitir_salto(marco["cuerpo"])
            self.gen.programa.emitir_etiqueta(marco["paso"])
        elif self._es_condicion_de_dowhile(ctx):
            # La condición del do-while va al final.
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
            # El paso ya está traducido: vuelve al inicio
            # y marca dónde empieza el cuerpo. Su valor ya
            # está asignado, así que el temporal sobra.
            marco = self._ciclos[-1]
            self.gen.liberar(self.valor_de[id(ctx)])
            programa = self.gen.programa
            programa.emitir_salto(marco["inicio"])
            programa.emitir_etiqueta(marco["cuerpo"])
        elif self._es_sujeto_de_switch(ctx):
            # El sujeto vive todo el switch (se libera al
            # cerrarlo).
            self._switchs[-1]["sujeto"] = self.valor_de[id(ctx)]
        elif self._es_valor_de_case(ctx):
            # El caso se evalúa solo si los anteriores
            # no cuadraron (§2 del doc).
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
            # Condición del ciclo desarmado: índice < length.
            # El índice y el arreglo viven todo el ciclo.
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
        """[a, b, c] -> t = newarray 3; t[0] = a; t[1] = b; t[2] = c.

        El temporal del arreglo se pide ANTES de liberar los elementos:
        si no, podría reciclar el temporal de un elemento y el newarray
        lo pisaría antes de escribirlo en su posición.
        """
        elementos = [self._valor(e) for e in ctx.expression()]
        programa = self.gen.programa
        arreglo = self.gen.nuevo_temporal()
        programa.emitir_nuevo_arreglo(len(elementos), arreglo)
        for posicion, elemento in enumerate(elementos):
            programa.emitir_escritura_indice(arreglo, str(posicion),
                                             elemento)
        self.gen.liberar(*reversed(elementos))
        self.valor_de[id(ctx)] = arreglo

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
        """new C(a, b) -> t = new C; param t; param a; param b;
        call C.constructor, 3.

        El objeto viaja como primer 'param' (el receptor), así que el N del
        call lo cuenta. El constructor puede ser heredado; si ninguna clase
        de la cadena lo define, solo se reserva el objeto.
        """
        clase = ctx.Identifier().getText()
        argumentos = ([self._valor(e) for e in ctx.arguments().expression()]
                      if ctx.arguments() is not None else [])
        programa = self.gen.programa
        # El temporal del objeto se pide ANTES de liberar los argumentos:
        # si no, podría reciclar uno y el 'new' lo pisaría antes del call.
        objeto = self.gen.nuevo_temporal()
        programa.emitir_nuevo(clase, objeto)
        for ancestro in self._con_inicializadores(clase):
            programa.emitir_parametro(objeto)
            programa.emitir_llamada(f"{ancestro}.__atributos", 1)
        constructor, duena = self._buscar_miembro(clase, "constructor")
        if constructor is not None:
            programa.emitir_parametro(objeto)
            for argumento in argumentos:
                programa.emitir_parametro(argumento)
            programa.emitir_llamada(f"{duena}.constructor",
                                    len(argumentos) + 1)
        self.gen.liberar(*argumentos)
        self.valor_de[id(ctx)] = objeto

    def exitThisExpr(self, ctx):
        # 'this' es el nombre simbólico del receptor dentro de un método.
        self.valor_de[id(ctx)] = "this"

    def exitLeftHandSide(self, ctx):
        self._traducir_cadena(ctx, ctx.primaryAtom(), ctx.suffixOp())

    def _es_destino_de_asignacion(self, ctx) -> bool:
        """¿Este leftHandSide es el lado izquierdo de un '=' ?"""
        padre = ctx.parentCtx
        return (isinstance(padre, CompiscriptParser.AssignExprContext)
                and padre.leftHandSide() is ctx)

    # ------------------------------------------------------------------
    # Clases y herencia: solo lo necesario para resolver llamadas
    # ------------------------------------------------------------------

    def _scope_de_clase(self, nombre):
        for hijo in self.gen.tabla.global_scope.children:
            if hijo.kind == "class" and hijo.name == nombre:
                return hijo
        return None

    def _buscar_miembro(self, clase, nombre):
        """(símbolo, clase que lo declara) subiendo por la herencia, o
        (None, None). Es la misma búsqueda del análisis semántico: un
        método heredado se resuelve en el ancestro más cercano que lo
        define."""
        vistos = set()
        while clase and clase not in vistos:
            vistos.add(clase)
            scope = self._scope_de_clase(clase)
            simbolo = scope.resolve_local(nombre) if scope is not None else None
            if simbolo is not None:
                return simbolo, clase
            simbolo_clase = self.gen.tabla.global_scope.resolve_local(clase)
            clase = (simbolo_clase.extra.get("parent")
                     if simbolo_clase is not None else None)
        return None, None

    def _con_inicializadores(self, clase) -> list[str]:
        """Clases de la cadena de herencia con atributos inicializados, de
        la raíz hacia `clase`: los del padre se inicializan primero."""
        cadena, vistos = [], set()
        while clase and clase not in vistos:
            vistos.add(clase)
            cadena.append(clase)
            simbolo = self.gen.tabla.global_scope.resolve_local(clase)
            clase = simbolo.extra.get("parent") if simbolo is not None else None
        return [c for c in reversed(cadena) if c in self._clases_con_init]

    def _guardar_inicializador(self, campo: str, valor: str) -> None:
        """Saca de la salida el código del inicializador de un atributo y lo
        guarda para la función de inicialización de su clase."""
        programa = self.gen.programa
        codigo = programa.instrucciones[self._inicio_init:]
        del programa.instrucciones[self._inicio_init:]
        self.gen.liberar(valor)       # su temporal era del código global
        self._inits.setdefault(self._clase_actual(), []).append(
            (campo, valor, codigo))

    def _clase_actual(self):
        """Clase del método que se está traduciendo (el tipo de 'this')."""
        for ambito in reversed(self._ambitos):
            if ambito.kind == "class":
                return ambito.name
        return None

    def _tipo_de_atomo(self, atomo):
        """Tipo estático del primer elemento de una cadena, o None."""
        if isinstance(atomo, CompiscriptParser.NewExprContext):
            return atomo.Identifier().getText()
        if isinstance(atomo, CompiscriptParser.ThisExprContext):
            return self._clase_actual()
        simbolo, _ = self._buscar(atomo.Identifier().getText())
        return simbolo.type if simbolo is not None else None

    @staticmethod
    def _tipo_de_elemento(tipo):
        if isinstance(tipo, str) and tipo.endswith("[]"):
            return tipo[:-2]
        return None

    # ------------------------------------------------------------------
    # Cadenas de acceso: variable, llamada, índice, atributo y método
    # ------------------------------------------------------------------

    def _traducir_cadena(self, ctx, atomo, sufijos) -> None:
        """Traduce `atomo sufijo*`: a, f(x), a[i], p.campo, p.m(x), ...

        Cada sufijo consume la base anterior y deja el siguiente operando
        (normalmente un temporal que reutiliza el de la base). Se lleva el
        tipo estático para saber a qué método llama `obj.m()`.

        Como destino de '=', el ÚLTIMO sufijo (índice o atributo) no se lee:
        se anota (tipo, base, selector) para que exitAssignExpr emita la
        escritura `base[selector] = v` o `base.selector = v`.
        """
        programa = self.gen.programa
        Indice = CompiscriptParser.IndexExprContext
        Atributo = CompiscriptParser.PropertyAccessExprContext
        Llamada = CompiscriptParser.CallExprContext

        como_destino = (bool(sufijos)
                        and self._es_destino_de_asignacion(ctx)
                        and isinstance(sufijos[-1], (Indice, Atributo)))
        base = self._valor(atomo)
        tipo = self._tipo_de_atomo(atomo)
        hasta = len(sufijos) - 1 if como_destino else len(sufijos)

        i = 0
        if (isinstance(atomo, CompiscriptParser.IdentifierExprContext)
                and sufijos and isinstance(sufijos[0], Llamada)):
            # f(x): el tipo de una función es su tipo de retorno.
            base = self._traducir_llamada(atomo, sufijos[0])
            i = 1

        while i < hasta:
            sufijo = sufijos[i]
            if isinstance(sufijo, Indice):
                indice = self._valor(sufijo.expression())
                destino = self.gen.temporal_para(base, indice)
                programa.emitir_lectura_indice(base, indice, destino)
                base, tipo = destino, self._tipo_de_elemento(tipo)
            elif isinstance(sufijo, Atributo):
                nombre = sufijo.Identifier().getText()
                siguiente = sufijos[i + 1] if i + 1 < hasta else None
                if isinstance(siguiente, Llamada):
                    base, tipo = self._traducir_llamada_metodo(
                        base, tipo, nombre, siguiente)
                    i += 1
                else:
                    destino = self.gen.temporal_para(base)
                    programa.emitir_lectura_campo(base, nombre, destino)
                    simbolo, _ = self._buscar_miembro(tipo, nombre)
                    base = destino
                    tipo = simbolo.type if simbolo is not None else None
            else:
                base = self._gancho("llamada a un valor", ctx)
            i += 1

        if como_destino:
            ultimo = sufijos[-1]
            if isinstance(ultimo, Indice):
                self._lvalor[id(ctx)] = (
                    "indice", base, self._valor(ultimo.expression()))
            else:
                self._lvalor[id(ctx)] = (
                    "campo", base, ultimo.Identifier().getText())
        self.valor_de[id(ctx)] = base

    def _traducir_llamada(self, atomo, llamada) -> str:
        """param a_i en orden, luego 'call f, N'. Devuelve
        el operando resultado, o '_' si la función es void.

        Un método llamado por su nombre dentro de su propia clase tiene
        receptor implícito: se pasa 'this' como primer param."""
        nombre = atomo.Identifier().getText()
        # La tabla dejó su ámbito actual en el global:
        # se resuelve en el espejo de ámbitos del
        # recorrido (la función puede vivir en un
        # ámbito contenedor, no en el global).
        simbolo, ambito = self._buscar(nombre)
        argumentos = ([self._valor(e)
                       for e in llamada.arguments().expression()]
                      if llamada.arguments() is not None else [])
        programa = self.gen.programa
        es_metodo = ambito is not None and ambito.kind == "class"
        if es_metodo:
            programa.emitir_parametro("this")
        for argumento in argumentos:
            programa.emitir_parametro(argumento)
        # Los argumentos se liberan tras el call: el param
        # solo lee el operando y otro cómputo podría
        # reciclar su slot antes de que ejecute el call.
        void = not simbolo.type or simbolo.type == "void"
        destino = None if void else self.gen.nuevo_temporal()
        programa.emitir_llamada(self._nombre_de_funcion(simbolo),
                                 len(argumentos) + (1 if es_metodo else 0),
                                 destino)
        self.gen.liberar(*argumentos)
        return destino if destino else "_"

    def _traducir_llamada_metodo(self, receptor, clase, nombre, llamada):
        """obj.m(a, b) -> param obj; param a; param b; t = call C.m, 3.

        C es la clase que declara m: la estática del receptor o, si no la
        redefine, el ancestro más cercano que sí (enlace estático; el
        despacho dinámico queda para código objeto, DISENO_TAC.md §7).
        Devuelve (operando resultado o '_', tipo de retorno)."""
        simbolo, duena = self._buscar_miembro(clase, nombre)
        argumentos = ([self._valor(e)
                       for e in llamada.arguments().expression()]
                      if llamada.arguments() is not None else [])
        programa = self.gen.programa
        programa.emitir_parametro(receptor)
        for argumento in argumentos:
            programa.emitir_parametro(argumento)
        void = (simbolo is None or not simbolo.type
                or simbolo.type == "void")
        destino = None if void else self.gen.nuevo_temporal()
        cualificado = f"{duena}.{nombre}" if duena else nombre
        programa.emitir_llamada(cualificado, len(argumentos) + 1, destino)
        self.gen.liberar(*argumentos)
        self.gen.liberar(receptor)
        tipo = simbolo.type if simbolo is not None else None
        return (destino if destino else "_"), tipo

    def exitAssignExpr(self, ctx):
        lhs = ctx.leftHandSide()
        valor = self._valor(ctx.assignmentExpr())
        atomo = lhs.primaryAtom()
        lvalor = self._lvalor.pop(id(lhs), None)
        programa = self.gen.programa
        if lvalor is not None:
            # a[i] = v  o  p.campo = v: la base y el índice siguen vivos
            # desde que se tradujo el lado izquierdo; se liberan al escribir.
            clase, base, selector = lvalor
            if clase == "indice":
                programa.emitir_escritura_indice(base, selector, valor)
                self.gen.liberar(selector, base)
            else:
                programa.emitir_escritura_campo(base, selector, valor)
                self.gen.liberar(base)
        elif not lhs.suffixOp() and isinstance(
                atomo, CompiscriptParser.IdentifierExprContext):
            destino = self._destino(atomo.Identifier().getText())
            programa.emitir_asignacion(destino, valor)
        else:
            self._pendiente(f"asignación a {lhs.getText()}")
        # El valor lo libera quien consuma esta expresión (la
        # sentencia de asignación o la expresión padre).
        self.valor_de[id(ctx)] = valor

    def exitPropertyAssignExpr(self, ctx):
        valor = self._valor(ctx.assignmentExpr())
        objeto = self._valor(ctx.leftHandSide())
        self.gen.programa.emitir_escritura_campo(
            objeto, ctx.Identifier().getText(), valor)
        self.gen.liberar(objeto)
        self.valor_de[id(ctx)] = valor

    # ------------------------------------------------------------------
    # Declaraciones y sentencias
    # ------------------------------------------------------------------

    def _emitir_inicio_de_for(self, ctx) -> None:
        """El inicializador del 'for' ya está traducido:
        empieza la etiqueta de inicio (va después de él)."""
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

    def enterVariableDeclaration(self, ctx):
        if self._es_miembro_de_clase():
            self._inicio_init = len(self.gen.programa.instrucciones)

    def enterConstantDeclaration(self, ctx):
        if self._es_miembro_de_clase():
            self._inicio_init = len(self.gen.programa.instrucciones)

    def exitVariableDeclaration(self, ctx):
        if self._es_miembro_de_clase():
            if ctx.initializer() is not None:
                self._guardar_inicializador(
                    ctx.Identifier().getText(),
                    self._valor(ctx.initializer().expression()))
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
            self._guardar_inicializador(
                ctx.Identifier().getText(), self._valor(ctx.expression()))
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
            # expression '.' Identifier '=' expression ';'
            objeto = self._valor(exprs[0])
            valor = self._valor(exprs[1])
            self.gen.programa.emitir_escritura_campo(
                objeto, ctx.Identifier().getText(), valor)
            self.gen.liberar(valor, objeto)
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
        inicializadores = self._inits.pop(ctx.Identifier(0).getText(), [])
        if inicializadores:
            # Clase.__atributos: recibe el objeto como 'this' y deja cada
            # atributo con su valor inicial. Va después de los métodos.
            self.gen.entrar_funcion("__atributos")
            programa = self.gen.programa
            for campo, valor, codigo in inicializadores:
                programa.instrucciones.extend(codigo)
                programa.emitir_escritura_campo("this", campo, valor)
            self.gen.salir_funcion()
        self.gen.salir_clase()
        self._salir_ambito()

    def enterBlock(self, ctx):
        if self._es_cuerpo_de_funcion(ctx):
            return        # el ámbito de la función ya está abierto
        self._entrar_ambito("block")
        padre = ctx.parentCtx
        if isinstance(padre, CompiscriptParser.IfStatementContext):
            if ctx is padre.block(0):
                # 'then': si la condición es falsa, salta
                # al 'else' (o al fin, si no lo hay).
                marco = self._ifs[-1]
                condicion = self._valor(padre.expression())
                self.gen.liberar(condicion)
                self.gen.programa.emitir_salto_si_falso(
                    condicion, marco["otro"] or marco["fin"])
            else:
                # El 'else' empieza donde aterrizó el
                # salto del 'ifFalse'.
                self.gen.programa.emitir_etiqueta(
                    self._ifs[-1]["otro"])
        elif isinstance(padre, CompiscriptParser.WhileStatementContext):
            # 'while': si la condición es falsa, no
            # se ejecuta el cuerpo.
            marco = self._ciclos[-1]
            condicion = self._valor(padre.expression())
            self.gen.liberar(condicion)
            self.gen.programa.emitir_salto_si_falso(
                condicion, marco["fin"])
        elif isinstance(padre, CompiscriptParser.TryCatchStatementContext):
            if ctx is padre.block(1):
                # El 'catch' solo lo alcanza una excepción.
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
                # Fin del 'then': con 'else', salta al fin
                # para no caer en el bloque contrario.
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
                # Fin del 'try': el flujo normal salta
                # por encima del 'catch'.
                programa.emitir_salto(self._trys[-1]["fin"])
        self._salir_ambito()

    def enterForStatement(self, ctx):
        # El inicializador queda fuera del bloque: el
        # ciclo abre su propio ámbito.
        self._entrar_ambito("block")
        inicio = self.gen.nueva_etiqueta("for_inicio")
        fin = self.gen.nueva_etiqueta("for_fin")
        paso = self.gen.nueva_etiqueta("for_paso")
        cuerpo = self.gen.nueva_etiqueta("for_cuerpo")
        tiene_paso = (self._clasificar_expresiones_de_for(ctx)
                      .get("paso") is not None)
        # Sin paso, 'continue' y el fin del cuerpo
        # vuelven directo a la condición.
        volver = paso if tiene_paso else inicio
        self._ciclos.append({
            "inicio": inicio, "fin": fin, "paso": paso,
            "cuerpo": cuerpo, "volver": volver,
            # Hay inicializador: la etiqueta de inicio
            # se emite al terminar de traducirlo.
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
        # 'continue' salta a la condición (su etiqueta
        # se emite en enterExpression).
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
        # Se desarma en un ciclo indexado (§2 del doc).
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
        # Fin del caso: salta al fin y marca dónde
        # sigue la cadena de comparaciones.
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