// Herencia: atributos heredados, métodos redefinidos y constructor heredado.
class Animal {
  var nombre: string;
  function constructor(nombre: string) {
    this.nombre = nombre;
  }
  function hablar(): string {
    return this.nombre + " hace ruido";
  }
  function presentarse(): string {
    return "Soy " + this.nombre;
  }
}

class Perro : Animal {
  function hablar(): string {
    return this.nombre + " ladra";
  }
}

class Cachorro : Perro {
  function jugar(): string {
    return this.hablar() + " y juega";
  }
}

let c: Cachorro = new Cachorro("Toby");
print(c.hablar());
print(c.presentarse());
print(c.jugar());
