OPENQASM 3.0;
include "stdgates.inc";
bit[1] c;
qubit[2] q;
U(0.29863623560610975, -pi/2, pi/2) q[1];
c[0] = measure q[0];
