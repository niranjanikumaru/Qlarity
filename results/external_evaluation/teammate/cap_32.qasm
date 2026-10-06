OPENQASM 3.0;
include "stdgates.inc";
bit[1] c;
qubit[2] q;
U(pi/2, pi/4, -pi) q[0];
cx q[1], q[0];
c[0] = measure q[0];
if (c == 1) {
  U(0, pi/4, 0) q[1];
}
if (c == 0) {
} else {
  reset q[0];
  U(pi/2, pi/4, -pi) q[0];
  cx q[1], q[0];
  c[0] = measure q[0];
  if (c == 1) {
    U(0, pi/4, 0) q[1];
  }
}
if (c == 0) {
} else {
  reset q[0];
  U(pi/2, pi/4, -pi) q[0];
  cx q[1], q[0];
  c[0] = measure q[0];
  if (c == 1) {
    U(0, pi/4, 0) q[1];
  }
}
if (c == 0) {
} else {
  reset q[0];
  U(pi/2, pi/4, -pi) q[0];
  cx q[1], q[0];
  c[0] = measure q[0];
  if (c == 1) {
    U(0, pi/4, 0) q[1];
  }
}
if (c == 0) {
} else {
  reset q[0];
  U(pi/2, pi/4, -pi) q[0];
  cx q[1], q[0];
  c[0] = measure q[0];
  if (c == 1) {
    U(0, pi/4, 0) q[1];
  }
}
if (c == 0) {
} else {
  reset q[0];
  U(pi/2, pi/4, -pi) q[0];
  cx q[1], q[0];
  c[0] = measure q[0];
  if (c == 1) {
    U(0, pi/4, 0) q[1];
  }
}
if (c == 0) {
} else {
  reset q[0];
  U(pi/2, pi/4, -pi) q[0];
  cx q[1], q[0];
  c[0] = measure q[0];
  if (c == 1) {
    U(0, pi/4, 0) q[1];
  }
}
if (c == 0) {
} else {
  reset q[0];
  U(pi/2, pi/4, -pi) q[0];
  cx q[1], q[0];
  c[0] = measure q[0];
  if (c == 1) {
    U(0, pi/4, 0) q[1];
  }
}
if (c == 0) {
} else {
  reset q[0];
  U(pi/2, pi/4, -pi) q[0];
  cx q[1], q[0];
  c[0] = measure q[0];
  if (c == 1) {
    U(0, pi/4, 0) q[1];
  }
}
if (c == 0) {
} else {
  reset q[0];
  U(pi/2, pi/4, -pi) q[0];
  cx q[1], q[0];
  c[0] = measure q[0];
  if (c == 1) {
    U(0, pi/4, 0) q[1];
  }
}
if (c == 0) {
} else {
  reset q[0];
  U(pi/2, pi/4, -pi) q[0];
  cx q[1], q[0];
  c[0] = measure q[0];
  if (c == 1) {
    U(0, pi/4, 0) q[1];
  }
}
if (c == 0) {
} else {
  reset q[0];
  U(pi/2, pi/4, -pi) q[0];
  cx q[1], q[0];
  c[0] = measure q[0];
  if (c == 1) {
    U(0, pi/4, 0) q[1];
  }
}
if (c == 0) {
} else {
  reset q[0];
  U(pi/2, pi/4, -pi) q[0];
  cx q[1], q[0];
  c[0] = measure q[0];
  if (c == 1) {
    U(0, pi/4, 0) q[1];
  }
}
if (c == 0) {
} else {
  reset q[0];
  U(pi/2, pi/4, -pi) q[0];
  cx q[1], q[0];
  c[0] = measure q[0];
  if (c == 1) {
    U(0, pi/4, 0) q[1];
  }
}
if (c == 0) {
} else {
  reset q[0];
  U(pi/2, pi/4, -pi) q[0];
  cx q[1], q[0];
  c[0] = measure q[0];
  if (c == 1) {
    U(0, pi/4, 0) q[1];
  }
}
if (c == 0) {
} else {
  reset q[0];
  U(pi/2, pi/4, -pi) q[0];
  cx q[1], q[0];
  c[0] = measure q[0];
  if (c == 1) {
    U(0, pi/4, 0) q[1];
  }
}
if (c == 0) {
} else {
  reset q[0];
  U(pi/2, pi/4, -pi) q[0];
  cx q[1], q[0];
  c[0] = measure q[0];
  if (c == 1) {
    U(0, pi/4, 0) q[1];
  }
}
if (c == 0) {
} else {
  reset q[0];
  U(pi/2, pi/4, -pi) q[0];
  cx q[1], q[0];
  c[0] = measure q[0];
  if (c == 1) {
    U(0, pi/4, 0) q[1];
  }
}
if (c == 0) {
} else {
  reset q[0];
  U(pi/2, pi/4, -pi) q[0];
  cx q[1], q[0];
  c[0] = measure q[0];
  if (c == 1) {
    U(0, pi/4, 0) q[1];
  }
}
if (c == 0) {
} else {
  reset q[0];
  U(pi/2, pi/4, -pi) q[0];
  cx q[1], q[0];
  c[0] = measure q[0];
  if (c == 1) {
    U(0, pi/4, 0) q[1];
  }
}
if (c == 0) {
} else {
  reset q[0];
  U(pi/2, pi/4, -pi) q[0];
  cx q[1], q[0];
  c[0] = measure q[0];
  if (c == 1) {
    U(0, pi/4, 0) q[1];
  }
}
if (c == 0) {
} else {
  reset q[0];
  U(pi/2, pi/4, -pi) q[0];
  cx q[1], q[0];
  c[0] = measure q[0];
  if (c == 1) {
    U(0, pi/4, 0) q[1];
  }
}
if (c == 0) {
} else {
  reset q[0];
  U(pi/2, pi/4, -pi) q[0];
  cx q[1], q[0];
  c[0] = measure q[0];
  if (c == 1) {
    U(0, pi/4, 0) q[1];
  }
}
if (c == 0) {
} else {
  reset q[0];
  U(pi/2, pi/4, -pi) q[0];
  cx q[1], q[0];
  c[0] = measure q[0];
  if (c == 1) {
    U(0, pi/4, 0) q[1];
  }
}
if (c == 0) {
} else {
  reset q[0];
  U(pi/2, pi/4, -pi) q[0];
  cx q[1], q[0];
  c[0] = measure q[0];
  if (c == 1) {
    U(0, pi/4, 0) q[1];
  }
}
if (c == 0) {
} else {
  reset q[0];
  U(pi/2, pi/4, -pi) q[0];
  cx q[1], q[0];
  c[0] = measure q[0];
  if (c == 1) {
    U(0, pi/4, 0) q[1];
  }
}
if (c == 0) {
} else {
  reset q[0];
  U(pi/2, pi/4, -pi) q[0];
  cx q[1], q[0];
  c[0] = measure q[0];
  if (c == 1) {
    U(0, pi/4, 0) q[1];
  }
}
if (c == 0) {
} else {
  reset q[0];
  U(pi/2, pi/4, -pi) q[0];
  cx q[1], q[0];
  c[0] = measure q[0];
  if (c == 1) {
    U(0, pi/4, 0) q[1];
  }
}
if (c == 0) {
} else {
  reset q[0];
  U(pi/2, pi/4, -pi) q[0];
  cx q[1], q[0];
  c[0] = measure q[0];
  if (c == 1) {
    U(0, pi/4, 0) q[1];
  }
}
if (c == 0) {
} else {
  reset q[0];
  U(pi/2, pi/4, -pi) q[0];
  cx q[1], q[0];
  c[0] = measure q[0];
  if (c == 1) {
    U(0, pi/4, 0) q[1];
  }
}
if (c == 0) {
} else {
  reset q[0];
  U(pi/2, pi/4, -pi) q[0];
  cx q[1], q[0];
  c[0] = measure q[0];
  if (c == 1) {
    U(0, pi/4, 0) q[1];
  }
}
if (c == 0) {
} else {
  reset q[0];
  U(pi/2, pi/4, -pi) q[0];
  cx q[1], q[0];
  c[0] = measure q[0];
  if (c == 1) {
    U(0, pi/4, 0) q[1];
  }
}
