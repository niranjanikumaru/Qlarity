OPENQASM 3.0;
include "stdgates.inc";
qubit[2] q;
h q[0];
t q[0];
cx q[1], q[0];

