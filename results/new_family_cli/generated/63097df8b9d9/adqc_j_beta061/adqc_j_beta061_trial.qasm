OPENQASM 3.0;
include "stdgates.inc";
qubit[2] q;
U(pi/2, 0, pi) q[0];
U(pi/2, 0, pi) q[1];
cx q[0], q[1];
U(0.6100000000000002, pi/2, -pi/2) q[0];
