// Ejemplo: complejidad media con errores léxicos intencionales.
// Los caracteres inválidos se descartan y el análisis continúa:
// se reportan 5 errores léxicos y ninguno sintáctico.

let saldo: integer = 100;
let nombre: string = "ana";

function calcular(n: integer): integer {
  return n * 2;
}

~~~

let texto = 'malito';
@
let limite: integer = 50;
#
print(calcular(limite) + saldo);
