OPENQASM 3.0;
include "stdgates.inc";
bit[1] c;
qubit[2] q;
U(pi/2, 0, 0) q[0];
c[0] = measure q[0];
if (!c[0]) {
  U(pi/2, 0, 2.5315926535897937) q[1];
}
if (c[0]) {
  reset q[0];
  U(pi/2, 0, 0) q[0];
  c[0] = measure q[0];
  if (!c[0]) {
    U(pi/2, 0, 2.5315926535897937) q[1];
  }
}
if (c[0]) {
  reset q[0];
  U(pi/2, 0, 0) q[0];
  c[0] = measure q[0];
  if (!c[0]) {
    U(pi/2, 0, 2.5315926535897937) q[1];
  }
}
if (c[0]) {
  reset q[0];
  U(pi/2, 0, 0) q[0];
  c[0] = measure q[0];
  if (!c[0]) {
    U(pi/2, 0, 2.5315926535897937) q[1];
  }
}
if (c[0]) {
  reset q[0];
  U(pi/2, 0, 0) q[0];
  c[0] = measure q[0];
  if (!c[0]) {
    U(pi/2, 0, 2.5315926535897937) q[1];
  }
}
if (c[0]) {
  reset q[0];
  U(pi/2, 0, 0) q[0];
  c[0] = measure q[0];
  if (!c[0]) {
    U(pi/2, 0, 2.5315926535897937) q[1];
  }
}
if (c[0]) {
  reset q[0];
  U(pi/2, 0, 0) q[0];
  c[0] = measure q[0];
  if (!c[0]) {
    U(pi/2, 0, 2.5315926535897937) q[1];
  }
}
