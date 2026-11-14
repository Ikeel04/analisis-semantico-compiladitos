// Ensamblador: expresiones aritméticas y lógicas.
let a: integer = 6;
let b: integer = 4;
let c: integer = 3;

// Aritméticas: precedencia, inmediatos (addiu), división y módulo con signo,
// multiplicación por potencia de 2 (la mirilla la cambia por sll).
print(a + b * c);
print((a + b) * (c + 2) - (a - b));
print(-a + b % c);
print(a / b - c * 2);
print(-17 / 5);
print(-17 % 5);
print(a * 8);

// Lógicas y relacionales.
let x: integer = 5;
let y: integer = 10;
let ok: boolean = x < y && y > 3;
print(ok);
print(x == 5 || y == 0);
print(!(x >= y));
print((x != y && !ok) || x > y);
print(x <= 5 && y >= 10);

// Float.
let f: float = 2.5;
print(f * 4 + 1.5);
print(f / 2.0 - 0.25);
print(f > 2.0);
print(-f);
