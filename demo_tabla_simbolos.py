"""
Demo en vivo de la tabla de símbolos, para la revisión funcional.
Corre: python3 demo_tabla_simbolos.py   (desde la raíz del repo)

Cada bloque corresponde 1 a 1 con un punto de la rúbrica:
  - Insertar                (2 pts)
  - Recuperar información   (2 pts)
  - Actualizar información  (2 pts)
  - Manejo de alcances      (3 pts)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src" / "semantic"))

from symbol_table import SymbolTable, SemanticError


def linea(titulo):
    print(f"\n=== {titulo} ===")


st = SymbolTable()

# ---------------------------------------------------------------------
linea("1) INSERTAR")
sym = st.insert("edad", "variable", type_="integer")
print(f"Insertado: {sym}")

print("Insertar el mismo nombre en el mismo ámbito debe fallar (redeclaración):")
try:
    st.insert("edad", "variable", type_="string")
except SemanticError as e:
    print(f"  -> Error esperado: {e}")

# ---------------------------------------------------------------------
linea("2) RECUPERAR")
print("lookup('edad') ->", st.lookup("edad"))
print("lookup('no_existe') ->", st.lookup("no_existe"), "(no declarado, no revienta)")

# ---------------------------------------------------------------------
linea("3) ACTUALIZAR")
print("Antes de actualizar:", st.lookup("edad"))
st.update("edad", type_="float")
print("Después de update(type_='float'):", st.lookup("edad"))

print("Actualizar algo que no existe debe fallar:")
try:
    st.update("fantasma", type_="integer")
except SemanticError as e:
    print(f"  -> Error esperado: {e}")

# ---------------------------------------------------------------------
linea("4) MANEJO DE ÁMBITOS")
st.insert("global_var", "variable", type_="integer")

st.enter_scope("function", name="calcular")
st.insert("local_var", "variable", type_="integer")
print("Dentro de la función 'calcular':")
print("  ve la global ->", st.lookup("global_var"))
print("  ve su local  ->", st.lookup("local_var"))

st.enter_scope("block", name="if-interno")
st.insert("local_var", "variable", type_="string")  # sombra válida
print("Dentro de un bloque anidado (mismo nombre, otro ámbito):")
print("  local_var ahora resuelve a ->", st.lookup("local_var"))
st.exit_scope()

print("Al salir del bloque, vuelve a ver la de la función:")
print("  local_var ->", st.lookup("local_var"))
st.exit_scope()

print("Al salir de la función, 'local_var' ya no existe:")
print("  local_var ->", st.lookup("local_var"))

print("\nÁrbol de ámbitos completo:")
print(st.describe_tree())
