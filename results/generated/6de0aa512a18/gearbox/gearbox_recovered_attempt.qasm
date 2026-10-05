OPENQASM 3.0;
include "stdgates.inc";
bit[1] c;
qubit[2] q;
U(2.4015926535897933, 0, -pi) q[0];
U(pi/2, pi/2, -pi/2) q[1];
cx q[0], q[1];
U(2.401592653589793, 0, -pi/2) q[0];
U(pi/2, pi/2, -pi/2) q[1];
c[0] = measure q[0];
if (c == 1) {
  U(pi/2, -pi/2, pi/2) q[1];
}
