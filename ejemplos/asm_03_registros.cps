// Selección de registros: hay 17 registros asignables ($t0-$t9, $s0-$s6).
// Esta expresión mantiene vivos más valores que registros, así que getReg
// tiene que desalojar (guardar en memoria) y volver a cargar.
let v0: integer = 0;
let v1: integer = 1;
let v2: integer = 2;
let v3: integer = 3;
let v4: integer = 4;
let v5: integer = 5;
let v6: integer = 6;
let v7: integer = 7;
let v8: integer = 8;
let v9: integer = 9;
let v10: integer = 10;
let v11: integer = 11;
let v12: integer = 12;
let v13: integer = 13;
let v14: integer = 14;
let v15: integer = 15;
let v16: integer = 16;
let v17: integer = 17;
let v18: integer = 18;
let v19: integer = 19;

let total: integer = (v0 * v0) + (v1 * v1) + (v2 * v2) + (v3 * v3) + (v4 * v4)
  + (v5 * v5) + (v6 * v6) + (v7 * v7) + (v8 * v8) + (v9 * v9)
  + (v10 * v10) + (v11 * v11) + (v12 * v12) + (v13 * v13) + (v14 * v14)
  + (v15 * v15) + (v16 * v16) + (v17 * v17) + (v18 * v18) + (v19 * v19);
print(total);

// Reutilización: x = x + 1 se queda en el mismo registro.
let cuenta: integer = 0;
cuenta = cuenta + 1;
cuenta = cuenta + 1;
cuenta = cuenta * 3;
print(cuenta);
