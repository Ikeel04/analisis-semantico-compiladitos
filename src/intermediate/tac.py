"""
Representación del código intermedio: cuádruplos (op, arg1, arg2, resultado).

Es el vocabulario común del equipo: la traducción del árbol se escribe encima
llamando a los métodos `emitir_*` de ProgramaTAC. El diseño y los esquemas de
traducción están en docs/DISENO_TAC.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Operaciones. Se declaran como constantes para que nadie escriba la cadena a
# mano: un error de dedo en "ifFalse" sería invisible hasta la demostración.

ASIGNAR = "="

SUMA = "+"
RESTA = "-"
MULTIPLICACION = "*"
DIVISION = "/"
MODULO = "%"
IGUAL = "=="
DISTINTO = "!="
MENOR = "<"
MENOR_IGUAL = "<="
MAYOR = ">"
MAYOR_IGUAL = ">="
Y_LOGICO = "&&"
O_LOGICO = "||"

BINARIAS = {SUMA, RESTA, MULTIPLICACION, DIVISION, MODULO,
            IGUAL, DISTINTO, MENOR, MENOR_IGUAL, MAYOR, MAYOR_IGUAL,
            Y_LOGICO, O_LOGICO}

NEGATIVO = "-u"       # sufijo para no confundir el menos unario con la resta
NEGACION = "!"

UNARIAS = {NEGATIVO, NEGACION}

ETIQUETA = "label"
SALTAR = "goto"
SALTAR_SI = "if"
SALTAR_SI_FALSO = "ifFalse"

INICIO_FUNCION = "function"
FIN_FUNCION = "endfunction"
PARAMETRO = "param"
LLAMAR = "call"       # (call, nombre, cantidad_args, destino)
RETORNAR = "return"

LEER_INDICE = "=[]"
ESCRIBIR_INDICE = "[]="    # (]=, indice, valor, arreglo): el arreglo es el destino

NUEVO = "new"
LEER_CAMPO = "=."
ESCRIBIR_CAMPO = ".="      # (.=, campo, valor, objeto): el objeto es el destino

PRINT = "print"            # (print, a, _, _): imprime el valor de a
LONGITUD = "length"        # (length, a, _, t1): t1 = length a (tamaño del arreglo)

COMENTARIO = "#"


@dataclass
class Cuadruplo:
    """Una instrucción de tres direcciones.

    Los cuatro campos existen siempre; los que la operación no usa quedan en
    None y se imprimen como '_' en la vista de cuádruplos del IDE.
    """

    op: str
    arg1: str | None = None
    arg2: str | None = None
    resultado: str | None = None

    def __str__(self) -> str:
        op = self.op
        if op == ETIQUETA:
            return f"{self.arg1}:"
        if op == ASIGNAR:
            return f"{self.resultado} = {self.arg1}"
        if op in BINARIAS:
            return f"{self.resultado} = {self.arg1} {op} {self.arg2}"
        if op == NEGATIVO:
            return f"{self.resultado} = -{self.arg1}"
        if op == NEGACION:
            return f"{self.resultado} = !{self.arg1}"
        if op == SALTAR:
            return f"goto {self.resultado}"
        if op == SALTAR_SI:
            return f"if {self.arg1} goto {self.resultado}"
        if op == SALTAR_SI_FALSO:
            return f"ifFalse {self.arg1} goto {self.resultado}"
        if op == INICIO_FUNCION:
            return f"function {self.arg1}:"
        if op == FIN_FUNCION:
            return f"endfunction {self.arg1}"
        if op == PARAMETRO:
            return f"param {self.arg1}"
        if op == LLAMAR:
            llamada = f"call {self.arg1}, {self.arg2}"
            return f"{self.resultado} = {llamada}" if self.resultado else llamada
        if op == RETORNAR:
            return "return" if self.arg1 is None else f"return {self.arg1}"
        if op == LEER_INDICE:
            return f"{self.resultado} = {self.arg1}[{self.arg2}]"
        if op == ESCRIBIR_INDICE:
            return f"{self.resultado}[{self.arg1}] = {self.arg2}"
        if op == NUEVO:
            return f"{self.resultado} = new {self.arg1}"
        if op == LEER_CAMPO:
            return f"{self.resultado} = {self.arg1}.{self.arg2}"
        if op == ESCRIBIR_CAMPO:
            return f"{self.resultado}.{self.arg1} = {self.arg2}"
        if op == PRINT:
            return f"print {self.arg1}"
        if op == LONGITUD:
            return f"{self.resultado} = length {self.arg1}"
        if op == COMENTARIO:
            return f"# {self.arg1}"
        return f"{op} {self.arg1} {self.arg2} {self.resultado}"

    @property
    def es_etiqueta(self) -> bool:
        return self.op == ETIQUETA

    def como_tupla(self) -> tuple:
        campo = lambda v: "_" if v is None else str(v)
        return (self.op, campo(self.arg1), campo(self.arg2), campo(self.resultado))


@dataclass
class ProgramaTAC:
    """Lista ordenada de cuádruplos, con la API que usa el generador."""

    instrucciones: list[Cuadruplo] = field(default_factory=list)

    def emitir(self, op, arg1=None, arg2=None, resultado=None) -> Cuadruplo:
        """Devuelve el cuádruplo agregado, por si hay que parchearlo después."""
        cuadruplo = Cuadruplo(op, arg1, arg2, resultado)
        self.instrucciones.append(cuadruplo)
        return cuadruplo

    def parchear(self, cuadruplo: Cuadruplo, destino: str) -> None:
        """Completa el destino de un salto emitido hacia adelante."""
        cuadruplo.resultado = destino

    def emitir_asignacion(self, destino, fuente) -> Cuadruplo:
        return self.emitir(ASIGNAR, fuente, None, destino)

    def emitir_binaria(self, op, izquierda, derecha, destino) -> Cuadruplo:
        return self.emitir(op, izquierda, derecha, destino)

    def emitir_unaria(self, op, operando, destino) -> Cuadruplo:
        return self.emitir(op, operando, None, destino)

    def emitir_etiqueta(self, etiqueta) -> Cuadruplo:
        return self.emitir(ETIQUETA, etiqueta)

    def emitir_salto(self, etiqueta) -> Cuadruplo:
        return self.emitir(SALTAR, None, None, etiqueta)

    def emitir_salto_si(self, condicion, etiqueta) -> Cuadruplo:
        return self.emitir(SALTAR_SI, condicion, None, etiqueta)

    def emitir_salto_si_falso(self, condicion, etiqueta) -> Cuadruplo:
        return self.emitir(SALTAR_SI_FALSO, condicion, None, etiqueta)

    def emitir_inicio_funcion(self, nombre) -> Cuadruplo:
        return self.emitir(INICIO_FUNCION, nombre)

    def emitir_fin_funcion(self, nombre) -> Cuadruplo:
        return self.emitir(FIN_FUNCION, nombre)

    def emitir_parametro(self, valor) -> Cuadruplo:
        return self.emitir(PARAMETRO, valor)

    def emitir_llamada(self, nombre, cantidad_args, destino=None) -> Cuadruplo:
        return self.emitir(LLAMAR, nombre, cantidad_args, destino)

    def emitir_retorno(self, valor=None) -> Cuadruplo:
        return self.emitir(RETORNAR, valor)

    def emitir_lectura_indice(self, arreglo, indice, destino) -> Cuadruplo:
        return self.emitir(LEER_INDICE, arreglo, indice, destino)

    def emitir_escritura_indice(self, arreglo, indice, valor) -> Cuadruplo:
        return self.emitir(ESCRIBIR_INDICE, indice, valor, arreglo)

    def emitir_nuevo(self, clase, destino) -> Cuadruplo:
        return self.emitir(NUEVO, clase, None, destino)

    def emitir_lectura_campo(self, objeto, campo, destino) -> Cuadruplo:
        return self.emitir(LEER_CAMPO, objeto, campo, destino)

    def emitir_escritura_campo(self, objeto, campo, valor) -> Cuadruplo:
        return self.emitir(ESCRIBIR_CAMPO, campo, valor, objeto)

    def emitir_print(self, valor) -> Cuadruplo:
        return self.emitir(PRINT, valor)

    def emitir_longitud(self, arreglo, destino) -> Cuadruplo:
        return self.emitir(LONGITUD, arreglo, None, destino)

    def emitir_comentario(self, texto) -> Cuadruplo:
        return self.emitir(COMENTARIO, texto)

    def __len__(self) -> int:
        return len(self.instrucciones)

    def __iter__(self):
        return iter(self.instrucciones)

    def __getitem__(self, indice):
        return self.instrucciones[indice]

    def como_texto(self, numerar: bool = False) -> str:
        """El TAC como lo ve el usuario: etiquetas al margen, resto indentado."""
        lineas = []
        for i, cuadruplo in enumerate(self.instrucciones):
            texto = str(cuadruplo)
            if not cuadruplo.es_etiqueta:
                texto = "    " + texto
            lineas.append(f"{i:>4}  {texto}" if numerar else texto)
        return "\n".join(lineas)

    def filas_para_ide(self) -> list[dict]:
        filas = []
        for i, c in enumerate(self.instrucciones):
            op, arg1, arg2, resultado = c.como_tupla()
            filas.append({
                "#": i,
                "Operación": op,
                "Arg1": arg1,
                "Arg2": arg2,
                "Resultado": resultado,
                "Instrucción": str(c),
            })
        return filas
