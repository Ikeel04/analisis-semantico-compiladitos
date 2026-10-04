// Sentencias de control: if/else, while, do-while, for, foreach, switch, break y continue.
let n: integer = 3;
let total: integer = 0;

if (n > 2) {
  total = total + 1;
} else {
  total = total - 1;
}

while (n > 0) {
  n = n - 1;
  if (n == 1) {
    continue;
  }
  total = total + n;
}

do {
  total = total + 1;
} while (total < 5);

for (let i: integer = 0; i < 4; i = i + 1) {
  if (i == 3) {
    break;
  }
  total = total + i;
}

let notas: integer[] = [90, 70, 100];
foreach (nota in notas) {
  total = total + nota;
}

switch (total) {
  case 1:
    print("uno");
  case 2:
    print("dos");
  default:
    print("otro");
}
