OPENQASM 3.0;
include "stdgates.inc";
qubit[2] q;
U(2.4015926535897933, 0, -pi) q[0];
U(pi/2, pi/2, -pi/2) q[1];
cx q[0], q[1];
U(2.401592653589793, 0, -pi/2) q[0];
U(pi/2, pi/2, -pi/2) q[1];
