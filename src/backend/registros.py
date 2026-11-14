"""
Selección de registros: descriptores de registro y de dirección + getReg.

Es el algoritmo del Dragon Book (§8.6). El descriptor de registro dice qué
nombres tienen su valor en cada registro; el descriptor de dirección dice
dónde está el valor actual de cada nombre (registros y/o memoria). Un nombre
que no aparece en el descriptor de dirección está solo en memoria.

El asignador no conoce el TAC: el traductor le pasa, en cada llamada, una
función `vivo(nombre, pos)` con la información de vida (vida.py) y una función
`ubicacion(nombre)` que dice en qué dirección de memoria vive cada nombre.
"""

from __future__ import annotations

REGISTROS_ASIGNABLES = (tuple(f"$t{i}" for i in range(10))
                        + tuple(f"$s{i}" for i in range(7)))
MEMORIA = "mem"


class AsignadorRegistros:
    def __init__(self, programa, ubicacion, registros=REGISTROS_ASIGNABLES):
        self.programa = programa
        self.ubicacion = ubicacion          # nombre -> (dirección, es_byte)
        self.disponibles = tuple(registros)
        self.registros: dict[str, set] = {r: set() for r in self.disponibles}
        self.direcciones: dict[str, set] = {}
        self._turno = 0
        self.usados: set[str] = set()
        self.estadisticas = {"cargas": 0, "almacenamientos": 0,
                             "desalojos": 0, "aciertos": 0}

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------

    def ubicaciones(self, nombre) -> set:
        return self.direcciones.get(nombre, {MEMORIA})

    def en_memoria(self, nombre) -> bool:
        return MEMORIA in self.ubicaciones(nombre)

    def registro_de(self, nombre) -> str | None:
        for r in self.disponibles:
            if r in self.ubicaciones(nombre):
                return r
        return None

    def instantanea(self) -> str:
        """Descriptor de registros como texto: '$t0=t1,global+0 · $t1=fp+16*'.
        El asterisco marca los valores que la memoria todavía no tiene."""
        partes = []
        for r in self.disponibles:
            if self.registros[r]:
                nombres = ",".join(
                    n + ("" if self.en_memoria(n) else "*")
                    for n in sorted(self.registros[r]))
                partes.append(f"{r}={nombres}")
        return " · ".join(partes) if partes else "(vacío)"

    # ------------------------------------------------------------------
    # getReg
    # ------------------------------------------------------------------

    def leer(self, nombre, pos, vivo, protegidos=()) -> str:
        """Registro con el valor de `nombre`, cargándolo si no está en ninguno."""
        r = self.registro_de(nombre)
        if r is not None:
            self.estadisticas["aciertos"] += 1
            return r
        r = self._elegir(pos, vivo, protegidos)
        direccion, es_byte = self.ubicacion(nombre)
        self.programa.emitir("lbu" if es_byte else "lw", r, direccion,
                             comentario=f"cargar {nombre}")
        self.estadisticas["cargas"] += 1
        self.registros[r] = {nombre}
        self.direcciones[nombre] = {r, MEMORIA}
        self.usados.add(r)
        return r

    def para_resultado(self, destino, operandos, pos, vivo, protegidos=()) -> str:
        """Registro donde dejar el resultado de `destino = y op z`.

        `operandos` es una lista de (nombre, registro) ya cargados. Orden de
        preferencia: el registro de un operando que muere aquí (o que es el
        mismo destino), el registro que ya tenía el destino, uno libre, el de
        un operando que también está en memoria, y por último desalojar.
        """
        for nombre, r in operandos:
            if r in self.registros and self.registros[r] == {nombre} and (
                    nombre == destino or not vivo(nombre, pos)):
                return r
        anterior = self.registro_de(destino)
        if anterior is not None and self.registros[anterior] == {destino}:
            return anterior
        libre = self._libre(protegidos)
        if libre is not None:
            self.usados.add(libre)
            return libre
        for nombre, r in operandos:
            if (r in self.registros and self.registros[r] == {nombre}
                    and self.en_memoria(nombre)):
                return r
        return self._elegir(pos, vivo, protegidos)

    def _libre(self, protegidos) -> str | None:
        for r in self.disponibles:
            if not self.registros[r] and r not in protegidos:
                return r
        return None

    def _necesita_guardarse(self, nombre, registro, pos, vivo) -> bool:
        ubic = self.ubicaciones(nombre)
        if MEMORIA in ubic or (ubic - {registro}):
            return False
        return vivo(nombre, pos)

    def _elegir(self, pos, vivo, protegidos) -> str:
        libre = self._libre(protegidos)
        if libre is not None:
            self.usados.add(libre)
            return libre
        # Sin libres: el de menor costo (valores a guardar), recorriendo en
        # turno rotativo para no desalojar siempre el mismo.
        mejor = None
        total = len(self.disponibles)
        for k in range(total):
            r = self.disponibles[(self._turno + k) % total]
            if r in protegidos:
                continue
            costo = sum(1 for n in self.registros[r]
                        if self._necesita_guardarse(n, r, pos, vivo))
            if mejor is None or costo < mejor[0]:
                mejor = (costo, r)
        self._turno += 1
        registro = mejor[1]
        self._desalojar(registro, pos, vivo)
        self.usados.add(registro)
        return registro

    def _desalojar(self, registro, pos, vivo) -> None:
        for nombre in sorted(self.registros[registro]):
            if self._necesita_guardarse(nombre, registro, pos, vivo):
                self._guardar(nombre, registro, "desalojo")
            self.direcciones[nombre].discard(registro)
            if not self.direcciones[nombre]:
                del self.direcciones[nombre]
        self.registros[registro] = set()
        self.estadisticas["desalojos"] += 1

    def _guardar(self, nombre, registro, motivo) -> None:
        direccion, es_byte = self.ubicacion(nombre)
        self.programa.emitir("sb" if es_byte else "sw", registro, direccion,
                             comentario=f"{motivo}: {nombre}")
        self.estadisticas["almacenamientos"] += 1
        self.direcciones.setdefault(nombre, set()).add(MEMORIA)

    # ------------------------------------------------------------------
    # Actualización de descriptores
    # ------------------------------------------------------------------

    def escribir(self, destino, registro) -> None:
        """`registro` acaba de recibir el nuevo valor de `destino`."""
        for r in list(self.ubicaciones(destino)):
            if r != MEMORIA:
                self.registros[r].discard(destino)
        for otro in self.registros[registro]:
            if otro != destino:
                self.direcciones[otro].discard(registro)
                if not self.direcciones[otro]:
                    del self.direcciones[otro]
        self.registros[registro] = {destino}
        self.direcciones[destino] = {registro}
        self.usados.add(registro)

    def copiar(self, destino, registro) -> None:
        """`destino = y` con y en `registro`: no se emite nada, solo se anota."""
        if destino in self.registros[registro]:
            return
        for r in list(self.ubicaciones(destino)):
            if r != MEMORIA:
                self.registros[r].discard(destino)
        self.registros[registro].add(destino)
        self.direcciones[destino] = {registro}

    def olvidar(self, nombre) -> None:
        """Un temporal muerto libera sus registros sin guardarse."""
        for r in self.ubicaciones(nombre):
            if r != MEMORIA:
                self.registros[r].discard(nombre)
        self.direcciones.pop(nombre, None)

    def guardar_sucios(self, necesita, motivo="fin de bloque") -> None:
        """Guarda en memoria los valores que solo están en registro y que
        `necesita(nombre)` declara vivos."""
        for r in self.disponibles:
            for nombre in sorted(self.registros[r]):
                if not self.en_memoria(nombre) and necesita(nombre):
                    self._guardar(nombre, r, motivo)

    def invalidar(self) -> None:
        """Olvida todos los registros (inicio de bloque o después de un call).
        Quien llama ya guardó lo que hacía falta."""
        for r in self.disponibles:
            self.registros[r] = set()
        self.direcciones = {}
