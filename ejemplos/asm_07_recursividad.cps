// Ensamblador: recursividad — factorial con caso base en el control de flujo.
// Las etiquetas y los saltos ya están listos (Parte 2), así que la recursión por
// marcos con `ifFalse` para el caso base corre en MARS.
function factorial(n: integer): integer {
  if (n <= 1) { return 1; }
  return n * factorial(n - 1);
}

print(factorial(5));
