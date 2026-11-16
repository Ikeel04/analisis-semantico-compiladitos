// Ensamblador: cadenas en tiempo de ejecución. `+` llama a __concat (reserva
// len(a)+len(b)+1 bytes con sbrk y copia), y == / != entre cadenas comparan el
// contenido con __strcmp (no los punteros).
let saludo: string = "Hola";
let nombre: string = "Mundo";
let frase: string = saludo + ", " + nombre + "!";
print(frase);

function repetir(s: string, n: integer): string {
  if (n <= 0) {
    return "";
  }
  return s + repetir(s, n - 1);
}
print(repetir("ab", 3));

let linea: string = "";
for (let i: integer = 0; i < 5; i = i + 1) {
  linea = linea + "*";
}
print(linea);

let copia: string = "Hola" + "";
print(copia == saludo);
print(copia != saludo);
print(saludo == nombre);
print("abc" == "abd");

class Persona {
  var nombre: string;
  var apellido: string;
  function constructor(n: string, a: string) {
    nombre = n;
    apellido = a;
  }
  function completo(): string {
    return nombre + " " + apellido;
  }
}
let per: Persona = new Persona("Ada", "Lovelace");
print(per.completo());
if (per.completo() == "Ada Lovelace") {
  print("coinciden");
}

let partes: string[] = ["uno", "dos", "tres"];
let unidas: string = "";
foreach (pal in partes) {
  if (unidas != "") {
    unidas = unidas + "-";
  }
  unidas = unidas + pal;
}
print(unidas);
