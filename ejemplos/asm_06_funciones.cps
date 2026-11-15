// Ensamblador: enlace de acceso para funciones anidadas (variables capturadas).
// El llamador pasa su frame pointer como enlace en $v1; el prólogo de la función
// anidada lo guarda en su celda y las lecturas/resoluciones de capturas van por
// ese enlace.
function contador(): integer {
  var base: integer = 10;
  function interno(x: integer): integer { return base + x; }
  return interno(5);
}
print(contador());

function sumador(base: integer) {
  function interno(x: integer): integer { return base + x; }
  print(interno(2));
}
sumador(100);
