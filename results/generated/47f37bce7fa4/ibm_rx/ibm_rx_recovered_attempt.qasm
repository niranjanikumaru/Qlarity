OPENQASM 3.0;
include "stdgates.inc";
bit[2] c;
qubit[3] q;
U(pi/2, 0, pi) q[0];
U(pi/2, 0, pi) q[1];
U(0, pi/2, -pi/2) q[2];
cx q[1], q[2];
U(0, 0, -pi/4) q[2];
cx q[0], q[2];
U(0, 0, pi/4) q[2];
cx q[1], q[2];
U(0, 0, pi/4) q[1];
U(0, 0, -pi/4) q[2];
cx q[0], q[2];
cx q[0], q[1];
U(0, 0, pi/4) q[0];
U(0, 0, -pi/4) q[1];
cx q[0], q[1];
U(pi/2, -pi/2, 3*pi/4) q[2];
cx q[1], q[2];
U(0, 0, -pi/4) q[2];
cx q[0], q[2];
U(0, 0, pi/4) q[2];
cx q[1], q[2];
U(0, 0, pi/4) q[1];
U(0, 0, -pi/4) q[2];
cx q[0], q[2];
cx q[0], q[1];
U(0, 0, pi/4) q[0];
U(0, 0, -pi/4) q[1];
cx q[0], q[1];
U(pi/2, 0, pi) q[0];
U(pi/2, 0, pi) q[1];
U(0, pi/2, -pi/4) q[2];
c[0] = measure q[0];
c[1] = measure q[1];
if (c == 1) {
  U(pi, 3*pi/4, -pi/4) q[2];
}
if (c == 2) {
  U(pi, 3*pi/4, -pi/4) q[2];
}
if (c == 3) {
  U(pi, -pi/4, 3*pi/4) q[2];
}
