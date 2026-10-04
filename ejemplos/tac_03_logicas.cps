// Expresiones lógicas y relacionales.
let x: integer = 5;
let y: integer = 10;
let ok: boolean = x < y && y > 3;
let alguno: boolean = x == 5 || y == 0;
let negado: boolean = !(x >= y);
let mezcla: boolean = (x != y && !alguno) || ok;
print(ok);
print(alguno);
print(negado);
print(mezcla);
