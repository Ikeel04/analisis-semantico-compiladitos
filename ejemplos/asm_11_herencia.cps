// Ensamblador: herencia. Los atributos heredados van primero en la instancia
// (mismo offset en la clase base y en las derivadas), el constructor heredado
// se reutiliza, los métodos redefinidos se resuelven en el TAC (enlace
// estático) y Clase.__atributos inicializa los atributos con valor.
class Animal {
  var nombre: string;
  var patas: integer = 4;
  function constructor(nombre: string) {
    this.nombre = nombre;
  }
  function hablar(): string {
    return nombre + " hace ruido";
  }
  function describir(): string {
    return "Soy " + this.nombre;
  }
}

class Perro : Animal {
  var trucos: integer = 0;
  function hablar(): string {
    return this.nombre + " ladra";
  }
  function aprender() {
    trucos = trucos + 1;
  }
}

class Cachorro : Perro {
  var juguete: string = "pelota";
  function jugar(): string {
    return this.hablar() + " y juega con su " + juguete;
  }
}

class Ave : Animal {
  function constructor(nombre: string) {
    this.nombre = nombre;
    this.patas = 2;
  }
  function hablar(): string {
    return this.nombre + " pia";
  }
}

let a: Animal = new Animal("Gato");
print(a.hablar());

let c: Cachorro = new Cachorro("Toby");
print(c.hablar());
print(c.describir());
print(c.jugar());
print(c.patas);
c.aprender();
c.aprender();
print(c.trucos);

let b: Ave = new Ave("Piolin");
print(b.hablar());
print(b.patas);
print(b.describir());
