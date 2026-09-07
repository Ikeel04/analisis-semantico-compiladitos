// Ejemplo: complejidad media con errores sintácticos intencionales.
// Se reportan 3 errores sintácticos y ninguno léxico.

const MAX: integer = 10

class Cuenta {
  let saldo: integer;

  function depositar(cantidad: integer): integer
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

let cuenta: Cuenta = new Cuenta(100;
print(suma(MAX) + cuenta.saldo);
