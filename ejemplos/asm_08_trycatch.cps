// Ensamblador: try/catch — un error capturado (división por cero) se maneja.
// El `try` apila un frame con el catch; al fallar la división, `__lanzar`
// restaura el frame y salta al catch.
let a: integer = 10;
let b: integer = 0;
let resultado: integer = 0;

try {
  resultado = a / b;
} catch (err) {
  resultado = -1;
  print("Error atrapado");
}

print(resultado);
