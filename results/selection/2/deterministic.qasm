OPENQASM 3.0;
include "stdgates.inc";
bit[1] c;
qubit[2] q;
U(0, -1.1071487177940904, -1.1071487177940904) q[1];
c[0] = measure q[0];
