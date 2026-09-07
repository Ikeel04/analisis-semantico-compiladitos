// Ejemplo: complejidad media, sin errores léxicos ni sintácticos.
// Compilación de un archivo de entrada con complejidad media.

const MAX: integer = 10;

class Cuenta {
  let saldo: integer;

  function constructor(saldo: integer) {
    this.saldo = saldo;
  }

  function depositar(cantidad: integer): integer {
    this.saldo = this.saldo + cantidad;
    return this.saldo;
  }
}

function suma(n: integer): integer {
  let total: integer = 0;
  for (let i: integer = 0; i < n; i = i + 1) {
    total = total + i;
  }
  return total;
}

let cuenta: Cuenta = new Cuenta(100);
let numeros: integer[] = [1, 2, 3, 4, 5];
let i: integer = 0;

do {
  i = i + 1;
} while (i < 3);

switch (i) {
  case 1:
    print("uno");
  case 3:
    print("tres");
  default:
    print("otro");
}

try {
  cuenta.depositar(50);
} catch (e) {
  print("error");
}

while (i > 0) {
  i = i - 1;
}

foreach (n in numeros) {
  if (n % 2 == 0) {
    print(n);
  }
}

print(cuenta.depositar(25) + suma(MAX) + cuenta.saldo);
