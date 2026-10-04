// try / catch: el catch solo lo alcanza una excepción en tiempo de ejecución.
let lista: integer[] = [1, 2, 3];
let resultado: integer = 0;

try {
  let peligro: integer = lista[10];
  resultado = peligro;
} catch (err) {
  resultado = -1;
  print("Error atrapado");
}

print(resultado);
