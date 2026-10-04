// Arreglos: literal, lectura, escritura, matriz y foreach.
let notas: integer[] = [90, 85, 100];
let primera: integer = notas[0];

notas[1] = 70;

let i: integer = 2;
notas[i] = notas[i - 1] + 5;

let m: integer[][] = [[1, 2], [3, 4]];
let x: integer = m[1][0];
m[0][1] = x + 1;

let total: integer = 0;
foreach (n in notas) {
  total = total + n;
}
print(total);
