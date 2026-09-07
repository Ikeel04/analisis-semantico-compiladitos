// Ejemplo: complejidad media con errores SEMÁNTICOS (solo semánticos).
// Argumentos de tipo incorrecto en llamadas, condición no booleana,
// print de una expresión void, autocomparación y case duplicado.

class Cuenta {
  var saldo: integer;

  function constructor(initial: integer) {
    this.saldo = initial;
  }

  function depositar(cantidad: integer): integer {
    return cantidad;
  }
}

function factorial(n: integer): integer {
  return n * factorial("x");
}

function vacia() { }

function media() {
  var c = new Cuenta(10);
  var doble = c.depositar(true);
  var cantidad = c.depositar("a");
  var flag = doble == cantidad;

  if (factorial(5)) {
    print(flag);
  }

  print(vacia());

  var uno = 1;
  if (uno == uno) {
    print("repetido");
  }

  switch (uno) {
    case 1:
      print("uno");
    case 1:
      print("otro");
  }
}