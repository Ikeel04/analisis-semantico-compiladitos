// Recursividad: cada llamada tiene su propio registro de activación.
function factorial(n: integer): integer {
  if (n <= 1) {
    return 1;
  }
  return n * factorial(n - 1);
}

function fibonacci(n: integer): integer {
  if (n < 2) {
    return n;
  }
  return fibonacci(n - 1) + fibonacci(n - 2);
}

let f: integer = factorial(5);
let g: integer = fibonacci(6);
print(f);
print(g);
