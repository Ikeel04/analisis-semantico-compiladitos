// Ensamblador: declaración y asignación de variables y constantes.
// Booleanos con sb/lbu, enteros y cadenas con sw/lw, float en IEEE-754.
const LIMITE: integer = 100;
const SALUDO: string = "hola mips";
let edad: integer = 20;
var activo: boolean = true;
let precio: float = 9.5;
let entero_a_float: float = 3;
let sin_valor: integer;

sin_valor = LIMITE - 1;
edad = edad + 1;
activo = false;
precio = precio * 2.0;
print(LIMITE);
print(SALUDO);
print(edad);
print(activo);
print(precio);
print(entero_a_float);
print(sin_valor);
