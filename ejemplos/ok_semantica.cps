// Ejemplo: verificación semántica completa, sin errores.
// Ejercita tipos (integer/float/boolean/string), const, arreglos e índices,
// funciones (llamadas, retorno, recursión, función anidada que captura el
// entorno), control de flujo, clases/objetos (new, this, herencia) y print.

const MAX: integer = 100;

class Empleado {
  var nombre: string;
  var puntos: integer;

  function constructor(nombre: string) {
    this.nombre = nombre;
    this.puntos = 0;
  }

  function sumar(p: integer): integer {
    this.puntos = this.puntos + p;
    return this.puntos;
  }
}

function factorial(n: integer): integer {
  if (n <= 1) {
    return 1;
  }
  return n * factorial(n - 1);
}

function contador(): integer {
  var base: integer = 10;
  function interno(x: integer): integer {
    return base + x;
  }
  return interno(5);
}

let nombre: string = "ana";
let sueldo: float = 2500.5;
let extra: float = sueldo + MAX;
let activo: boolean = true;
let edades: integer[] = [22, 30, 41];
let conDecimales: float[] = [1.0, 2.5, 3];
let e: Empleado = new Empleado(nombre);

var i: integer = 0;
while (i < 3) {
  i = i + 1;
}

if (activo) {
  print(nombre);
}

for (var j: integer = 0; j < 5; j = j + 1) {
  if (j == 2) { continue; }
  if (j == 4) { break; }
  print(j);
}

foreach (edad in edades) {
  if (edad % 2 == 0) {
    print(edad);
  }
}

switch (i) {
  case 1:
    print("uno");
  default:
    print("otro");
}

try {
  e.sumar(10);
} catch (ex) {
  print("error");
}

print(e.sumar(5));
print(sueldo + e.sumar(MAX));
print(factorial(5));
print(contador());
print(edades[0] + conDecimales[1]);
print(extra);