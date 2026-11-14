// Registros de activación: cada llamada reserva su marco en la pila.
// Parámetros de varios tipos (boolean de 1 byte, float, string), locales,
// temporales vivos a través de una llamada y llamadas anidadas.
function mezcla(p: integer, q: boolean, r: integer, s: float): integer {
  var producto: integer = p * r;
  var negado: boolean = !q;
  print(negado);
  print(s);
  return producto + p - r;
}

function doble(v: integer): integer {
  return v * 2;
}

function cuadruple(v: integer): integer {
  return doble(doble(v));
}

function saludo(nombre: string): string {
  return nombre;
}

print(mezcla(6, true, 7, 1.25));
// doble(3) queda vivo en memoria mientras se calcula cuadruple(doble(1)).
print(cuadruple(5) + doble(3) * cuadruple(doble(1)));
print(saludo("marcos"));
let k: integer = 0;
k = cuadruple(k + 3);
print(k);
