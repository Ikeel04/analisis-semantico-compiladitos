// Ensamblador: arreglos en el heap ([longitud][e0][e1]...), lectura y
// escritura con verificación de límites, matrices, foreach, arreglos como
// parámetros y un índice fuera de rango atrapado con try/catch.
let notas: integer[] = [90, 85, 100, 40];
print(notas);

notas[3] = 60;
let i: integer = 1;
notas[i] = notas[i - 1] + 5;
print(notas[1]);

function suma(datos: integer[]): integer {
  let total: integer = 0;
  foreach (n in datos) {
    total = total + n;
  }
  return total;
}
print(suma(notas));

function mayor(datos: integer[]): integer {
  let m: integer = datos[0];
  let k: integer = 1;
  while (k < 4) {
    if (datos[k] > m) {
      m = datos[k];
    }
    k = k + 1;
  }
  return m;
}
print(mayor(notas));

let matriz: integer[][] = [[1, 2, 3], [4, 5, 6]];
matriz[1][2] = matriz[0][0] + matriz[1][1];
print(matriz[1][2]);
print(matriz);

let traza: integer = 0;
for (let f: integer = 0; f < 2; f = f + 1) {
  traza = traza + matriz[f][f];
}
print(traza);

let banderas: boolean[] = [true, false, true];
print(banderas);
let nombres: string[] = ["Ana", "Luis"];
print(nombres[1]);

try {
  print(notas[10]);
} catch (err) {
  print("indice fuera de rango atrapado");
}
print("fin");
