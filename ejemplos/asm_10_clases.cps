// Ensamblador: clases y objetos. new reserva la instancia con sbrk; los
// atributos se leen/escriben con su offset (boolean de 1 byte con lbu/sb);
// dentro de los métodos un atributo sin `this` es obj+N (N bytes del receptor).
class Punto {
  var x: integer;
  var y: integer;
  function constructor(x: integer, y: integer) {
    this.x = x;
    this.y = y;
  }
  function mover(dx: integer, dy: integer) {
    x = x + dx;
    y = y + dy;
  }
  function distancia(): integer {
    let ax: integer = x;
    let ay: integer = y;
    if (ax < 0) { ax = -ax; }
    if (ay < 0) { ay = -ay; }
    return ax + ay;
  }
}

class Cuenta {
  var titular: string;
  var saldo: integer = 100;
  var activa: boolean = true;
  function constructor(titular: string) {
    this.titular = titular;
  }
  function retirar(monto: integer): boolean {
    if (!activa || monto > saldo) {
      return false;
    }
    saldo = saldo - monto;
    return true;
  }
  function cerrar() {
    activa = false;
  }
}

let p: Punto = new Punto(3, -4);
print(p.x);
print(p.distancia());
p.mover(2, 10);
print(p.y);
p.x = p.x * 10;
print(p.x);

let c: Cuenta = new Cuenta("Ana");
print(c.titular);
print(c.saldo);
print(c.retirar(30));
print(c.retirar(500));
print(c.saldo);
c.cerrar();
print(c.activa);
print(c.retirar(1));

function total(a: Cuenta, b: Cuenta): integer {
  return a.saldo + b.saldo;
}
let d: Cuenta = new Cuenta("Luis");
print(total(c, d));

let puntos: Punto[] = [new Punto(1, 1), new Punto(5, 7)];
let q: Punto = puntos[1];
print(q.distancia());
