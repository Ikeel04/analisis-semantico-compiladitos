// Clases, objetos y herencia.
class Animal {
  var nombre: string;
  var edad: integer = 0;

  function constructor(nombre: string) {
    this.nombre = nombre;
  }

  function hablar(): string {
    return this.nombre;
  }

  function cumple(): integer {
    this.edad = this.edad + 1;
    return this.edad;
  }
}

class Perro : Animal {
  function hablar(): string {
    return this.nombre + " dice guau";
  }
}

class Gato : Animal { }

let p: Perro = new Perro("Toby");
let g: Gato = new Gato("Misi");

print(p.hablar());
print(g.hablar());

p.edad = 3;
let e: integer = p.cumple();

let perros: Perro[] = [p, new Perro("Rex")];
perros[1].edad = 5;
print(perros[1].nombre);
