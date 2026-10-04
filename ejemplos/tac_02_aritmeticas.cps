// Expresiones aritméticas: precedencia, paréntesis, unario y reciclaje de temporales.
let a: integer = 6;
let b: integer = 4;
let c: integer = 3;
let d: integer = 2;
let e: integer = 5;
let f: integer = 1;

let r1: integer = a + b * c;
let r2: integer = (a + b) * (c + d) - (e + f);
let r3: integer = -a + b % c;
let r4: integer = a / b - c * d;
print(r1);
print(r2);
print(r3);
print(r4);
