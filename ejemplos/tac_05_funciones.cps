// Funciones y parámetros: llamadas, retorno, void y función anidada.
function suma(a: integer, b: integer): integer {
  return a + b;
}

function saludar(nombre: string): string {
  return "Hola " + nombre;
}

function mostrar(valor: integer) {
  print(valor);
}

function contador(): integer {
  var base: integer = 10;
  function interno(x: integer): integer {
    return base + x;
  }
  return interno(5);
}

let r: integer = suma(2, 3);
let t: integer = suma(r, suma(1, 1));
let msg: string = saludar("Mundo");
mostrar(t);
let c: integer = contador();
