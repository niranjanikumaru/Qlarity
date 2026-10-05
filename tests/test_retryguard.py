import unittest,tempfile
from pathlib import Path
import numpy as np
from qiskit import QuantumCircuit
from retryguard.fixtures import fixtures,Routine,I
from retryguard.analysis import analyze,retry_cap,bounded_maps
from retryguard.compiler import compile_early_measure,compile_deterministic,save_qasm,corrected_source
from retryguard.verifier import verify,verify_source

class Contracts(unittest.TestCase):
    def test_source_contracts_and_repairs(self):
        for r in fixtures():
            with self.subTest(r.name):
                a=analyze(r);check=verify_source(corrected_source(r,a),r.target,a['p'])
                self.assertLess(max(check.values()),1e-9)
                raw=verify_source(corrected_source(r,a,False),r.target,a['p'])
                self.assertGreater(raw['timeout_residual'],.05)
                self.assertLess(raw['success_residual'],1e-9)
    def test_independent_known_success_probabilities(self):
        ps=[analyze(r)['p'] for r in fixtures()]
        self.assertTrue(np.allclose(ps,[5/8,5/8,np.cos(.37)**4+np.sin(.37)**4]))
    def test_cap_minimal_and_feasible(self):
        for p in [.5,.625,.77,.99,1]:
            n=retry_cap(p,.01,16);self.assertLessEqual((1-p)**n,.01+1e-14)
            if n>1:self.assertGreater((1-p)**(n-1),.01)
        with self.assertRaises(ValueError):retry_cap(.1,.001,2)
    def test_reject_information_leak(self):
        from scipy.linalg import null_space
        # Success is exactly scalar identity; resolved failure leaks basis information.
        ks=[np.sqrt(.5)*I,np.diag([np.sqrt(.5),0]),np.diag([0,np.sqrt(.5)]),np.zeros((2,2))]
        columns=np.zeros((8,2),complex)
        for j,k in enumerate(ks):columns[[j,j+4],:]=k
        unitary=np.zeros((8,8),complex);unitary[:,[0,4]]=columns
        unitary[:,[1,2,3,5,6,7]]=null_space(columns.conj().T)
        q=QuantumCircuit(3);q.unitary(unitary,[0,1,2])
        with self.assertRaisesRegex(ValueError,'Failure leaks information'):
            analyze(Routine('leak',q,I,'test','synthetic',''))
    def test_roundtrip_all_policies(self):
        with tempfile.TemporaryDirectory() as tmp:
            pth=Path(tmp)/'c.qasm'
            for r in fixtures():
                a=analyze(r)
                for n in [1,2,5]:
                    save_qasm(compile_early_measure(r.target,a['p'],n),pth)
                    self.assertLess(max(v for k,v in verify(pth,r.target,1-(1-a['p'])**n).items() if k.endswith('residual')),1e-9)
                save_qasm(compile_deterministic(r.target),pth)
                self.assertLess(verify(pth,r.target,1)['success_residual'],1e-9)
    def test_detect_timeout_reset_mutation(self):
        r=next(fixtures());a=analyze(r);q=compile_early_measure(r.target,a['p'],2)
        with q.if_test((q.clbits[0],False)):q.reset(1)
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'c.qasm';save_qasm(q,p);v=verify(p,r.target,1-(1-a['p'])**2)
            self.assertLess(v['success_residual'],1e-9);self.assertGreater(v['timeout_residual'],.01)
    def test_detect_controlled_phase_mutation(self):
        r=next(fixtures());q=compile_deterministic(-r.target)
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'c.qasm';save_qasm(q,p);self.assertGreater(verify(p,r.target,1)['success_residual'],.5)
    def test_detect_false_success_flag(self):
        r=next(fixtures());q=compile_early_measure(r.target,.625,1)
        q.x(2);q.measure(2,0)
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'c.qasm';save_qasm(q,p);self.assertGreater(verify(p,r.target,.625)['success_residual'],.1)
    def test_recurrence_matches_closed_form(self):
        r=next(fixtures());a=analyze(r);p=a['p']
        s,t=bounded_maps([np.sqrt(p)*r.target],[np.sqrt(1-p)*I],4)
        self.assertTrue(np.allclose(t,(1-p)**4*np.eye(4)))
        self.assertTrue(np.allclose(s,(1-(1-p)**4)*np.kron(r.target.conj(),r.target)))
if __name__=='__main__':unittest.main()
