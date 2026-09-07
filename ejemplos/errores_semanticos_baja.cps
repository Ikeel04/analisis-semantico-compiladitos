// Ejemplo: complejidad baja con errores SEMÁNTICOS intencionales.
// El código es sintácticamente válido: los errores son de tipos y de ámbito
// (asignación con tipo incorrecto, condición no booleana, índice no integer
// y variable no declarada).

let a: integer = "texto";
let flag: boolean = 42;
let arr: integer[] = [1];
var item = arr["cero"];
var saludo = nombreInexistente;

if (a) {
  print(saludo);
}