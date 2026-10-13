"""
Direcciones de memoria y registros de activación.

Completa la tabla de símbolos con lo que falta para generar código objeto:
dónde vive cada dato en tiempo de ejecución. Recorre el árbol de ámbitos que
dejó el análisis semántico y le asigna a cada símbolo un área, un
desplazamiento y un tamaño, y a cada función su registro de activación.

El modelo de memoria, la disposición del marco y los supuestos (tamaños de 64
bits, alineación, herencia) están en docs/DISENO_TAC.md.

No importa nada del paquete semantic: trabaja sobre cualquier objeto con la
forma de un Scope y de un Symbol, así que se puede probar sin compilar.
"""

from __future__ import annotations

from dataclasses import dataclass, field

TAMANO_REFERENCIA = 8    # punteros: cadenas, arreglos y objetos
TAMANO_PALABRA = 8

TAMANOS = {
    "integer": 4,
    "float": 8,
    "boolean": 1,
    "string": TAMANO_REFERENCIA,
    "null": TAMANO_REFERENCIA,
    "void": 0,
}

AREA_GLOBAL = "global"
AREA_PARAMETRO = "parametro"
AREA_LOCAL = "local"
AREA_ATRIBUTO = "atributo"

OFFSET_ENLACE_CONTROL = 0
OFFSET_DIRECCION_RETORNO = TAMANO_PALABRA
INICIO_PARAMETROS = 2 * TAMANO_PALABRA


def tamano_de(tipo) -> int:
    """Un tipo sin resolver se reserva como referencia, para no desalinear."""
    if not isinstance(tipo, str):
        return TAMANO_REFERENCIA
    if tipo.endswith("[]"):
        return TAMANO_REFERENCIA
    return TAMANOS.get(tipo, TAMANO_REFERENCIA)


def alinear(offset: int, tamano: int) -> int:
    """Siguiente desplazamiento donde cabe un dato de `tamano` bytes alineado."""
    if tamano <= 1:
        return offset
    alineacion = min(tamano, TAMANO_PALABRA)
    resto = offset % alineacion
    return offset if resto == 0 else offset + (alineacion - resto)


@dataclass
class RegistroActivacion:
    """El marco de pila que se reserva cada vez que se llama a una función.

        fp + 0    enlace de control
        fp + 8    dirección de retorno
        fp + 16   parámetros, locales, temporales
    """

    nombre: str
    parametros: list = field(default_factory=list)
    locales: list = field(default_factory=list)
    tamano_parametros: int = 0
    tamano_locales: int = 0
    temporales: int = 0
    tamano_temporales: int = 0

    @property
    def offset_locales(self) -> int:
        return INICIO_PARAMETROS + self.tamano_parametros

    @property
    def offset_temporales(self) -> int:
        return self.offset_locales + self.tamano_locales

    @property
    def tamano_total(self) -> int:
        return self.offset_temporales + self.tamano_temporales

    def fijar_temporales(self, cantidad: int) -> None:
        """Se llama DESPUÉS de generar el TAC de la función, con el pico del
        pool: antes de generar no se sabe cuántos temporales hacen falta."""
        self.temporales = cantidad
        self.tamano_temporales = cantidad * TAMANO_PALABRA

    def describe(self) -> str:
        lineas = [f"registro de activación de '{self.nombre}' "
                  f"({self.tamano_total} bytes)",
                  f"  fp+{OFFSET_ENLACE_CONTROL:<4} enlace de control",
                  f"  fp+{OFFSET_DIRECCION_RETORNO:<4} dirección de retorno"]
        for simbolo in self.parametros:
            lineas.append(f"  fp+{simbolo.offset:<4} {simbolo.name} "
                          f"(parámetro · {simbolo.type} · {simbolo.tamano}b)")
        for simbolo in self.locales:
            lineas.append(f"  fp+{simbolo.offset:<4} {simbolo.name} "
                          f"({simbolo.kind} · {simbolo.type} · {simbolo.tamano}b)")
        if self.temporales:
            lineas.append(f"  fp+{self.offset_temporales:<4} {self.temporales} "
                          f"temporal(es) ({self.tamano_temporales}b)")
        return "\n".join(lineas)


@dataclass
class ResumenMemoria:
    """Lo que produjo la asignación de direcciones, para el IDE y los tests."""

    tamano_global: int = 0
    registros: dict = field(default_factory=dict)    # función -> RegistroActivacion
    clases: dict = field(default_factory=dict)       # clase -> tamaño de instancia

    def filas_para_ide(self) -> list[dict]:
        filas = [{"Área": "global", "Elemento": "(variables globales)",
                  "Tamaño": f"{self.tamano_global} b", "Detalle": ""}]
        for nombre, tamano in sorted(self.clases.items()):
            filas.append({"Área": "objeto", "Elemento": f"class {nombre}",
                          "Tamaño": f"{tamano} b", "Detalle": "instancia en heap"})
        for nombre, registro in sorted(self.registros.items()):
            filas.append({
                "Área": "marco",
                "Elemento": f"function {nombre}",
                "Tamaño": f"{registro.tamano_total} b",
                "Detalle": (f"{len(registro.parametros)} parám · "
                            f"{len(registro.locales)} local(es) · "
                            f"{registro.temporales} temp"),
            })
        return filas

    def describe(self) -> str:
        lineas = [f"área global: {self.tamano_global} bytes"]
        for nombre, tamano in sorted(self.clases.items()):
            lineas.append(f"instancia de '{nombre}': {tamano} bytes")
        for _, registro in sorted(self.registros.items()):
            lineas.append(registro.describe())
        return "\n".join(lineas)


def _marcar(simbolo, area: str, offset: int, tamano: int) -> None:
    simbolo.area = area
    simbolo.offset = offset
    simbolo.tamano = tamano
    base = "global" if area == AREA_GLOBAL else ("obj" if area == AREA_ATRIBUTO else "fp")
    simbolo.direccion = f"{base}+{offset}"


def _es_dato(simbolo) -> bool:
    """Las funciones y las clases no ocupan memoria: su dirección es una
    etiqueta del código, no una celda de datos."""
    return simbolo.kind in ("variable", "constant", "parameter")


def _scopes_de_clase(global_scope) -> dict:
    return {hijo.name: hijo for hijo in global_scope.children if hijo.kind == "class"}


def _layout_de_clase(nombre, scopes_clase, global_scope, calculados) -> int:
    """Asigna desplazamientos a los atributos de una clase y devuelve su tamaño.

    Los heredados van primero, así una instancia de la subclase se puede usar
    donde se espera una de la base.
    """
    if nombre in calculados:
        return calculados[nombre]

    simbolo_clase = global_scope.resolve_local(nombre)
    padre = simbolo_clase.extra.get("parent") if simbolo_clase is not None else None
    calculados[nombre] = 0      # se marca antes de bajar, para cortar herencia circular
    offset = (_layout_de_clase(padre, scopes_clase, global_scope, calculados)
              if padre and padre in scopes_clase else 0)

    scope = scopes_clase.get(nombre)
    if scope is not None:
        for simbolo in scope.symbols.values():
            if not _es_dato(simbolo):
                continue
            tamano = tamano_de(simbolo.type)
            offset = alinear(offset, tamano)
            _marcar(simbolo, AREA_ATRIBUTO, offset, tamano)
            offset += tamano

    calculados[nombre] = offset
    return offset


def _asignar_en_bloques(scope, area: str, offset: int, acumulador=None) -> int:
    """Asigna desplazamientos a los datos de un ámbito y de sus bloques anidados.

    Un bloque no genera una llamada, solo delimita visibilidad: la variable de un
    `for` o la del `catch` vive en el marco de su función, o en el área global si
    el bloque está suelto en el programa principal. No baja a los ámbitos de
    función ni de clase, que tienen su propio marco o layout.
    """
    for simbolo in scope.symbols.values():
        if not _es_dato(simbolo) or simbolo.kind == "parameter":
            continue
        tamano = tamano_de(simbolo.type)
        offset = alinear(offset, tamano)
        _marcar(simbolo, area, offset, tamano)
        if acumulador is not None:
            acumulador.append(simbolo)
        offset += tamano
    for hijo in scope.children:
        if hijo.kind == "block":
            offset = _asignar_en_bloques(hijo, area, offset, acumulador)
    return offset


def asignar_direcciones(tabla) -> ResumenMemoria:
    """Asigna área, desplazamiento y tamaño a cada símbolo del programa.

    Corre sobre el árbol de ámbitos ya terminado, después del análisis semántico
    y antes de generar el TAC.
    """
    global_scope = tabla.global_scope
    resumen = ResumenMemoria()

    # Las clases van primero: el tamaño de una variable de tipo clase depende de
    # que su layout ya exista.
    scopes_clase = _scopes_de_clase(global_scope)
    calculados: dict[str, int] = {}
    for nombre in scopes_clase:
        _layout_de_clase(nombre, scopes_clase, global_scope, calculados)
    resumen.clases = dict(calculados)

    def recorrer_funciones(scope, prefijo=""):
        for hijo in scope.children:
            if hijo.kind == "function":
                nombre = f"{prefijo}{hijo.name}"
                registro = RegistroActivacion(nombre=nombre)

                offset = INICIO_PARAMETROS
                for simbolo in hijo.symbols.values():
                    if simbolo.kind != "parameter":
                        continue
                    tamano = tamano_de(simbolo.type)
                    offset = alinear(offset, tamano)
                    _marcar(simbolo, AREA_PARAMETRO, offset, tamano)
                    registro.parametros.append(simbolo)
                    offset += tamano
                registro.tamano_parametros = offset - INICIO_PARAMETROS

                fin = _asignar_en_bloques(hijo, AREA_LOCAL, registro.offset_locales,
                                          registro.locales)
                registro.tamano_locales = fin - registro.offset_locales

                hijo.registro = registro
                resumen.registros[nombre] = registro
                recorrer_funciones(hijo, prefijo=f"{nombre}.")
            elif hijo.kind == "class":
                recorrer_funciones(hijo, prefijo=f"{hijo.name}.")
            elif hijo.kind == "block":
                recorrer_funciones(hijo, prefijo)

    recorrer_funciones(global_scope)

    resumen.tamano_global = _asignar_en_bloques(global_scope, AREA_GLOBAL, 0)
    return resumen
