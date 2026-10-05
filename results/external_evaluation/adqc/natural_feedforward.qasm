OPENQASM 3.0;
include "stdgates.inc";
bit[1] c;
qubit[2] q;
U(pi/2, 0, pi) q[0];
U(pi/2, 0, pi) q[1];
cx q[0], q[1];
U(0.6100000000000003, pi/2, -pi/2) q[0];
c[0] = measure q[0];
if (c[0]) {
  U(pi, 0, pi) q[1];
}
