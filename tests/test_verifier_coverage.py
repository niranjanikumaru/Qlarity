"""Adversarial contracts and independent-oracle checks, including tiny timeouts."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from qiskit import QuantumCircuit
from retryguard import independent
from retryguard.compiler import compile_early_measure, compile_deterministic, compile_source_retry, save_qasm
from retryguard.fixtures import fixtures
from retryguard.analysis import analyze
from retryguard.verifier import verify, verify_source_retry, compare_branches, ideal_choi
from retryguard.validation import InputError


class StrongVerification(unittest.TestCase):
    def verify_circuit(self,q,target,p,n):
        timeout=(1-p)**n
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'c.qasm';save_qasm(q,path)
            return verify(path,target,1-timeout,timeout_probability=timeout)

    def reasons(self,result):
        return {(item['code'],item['branch'],item['engine']) for item in result['failures']}

    def test_rare_timeout_retained_and_certified(self):
        r=next(fixtures());p=.9;n=32
        result=self.verify_circuit(compile_early_measure(r.target,p,n),r.target,p,n)
        self.assertTrue(result['verified'],result['failures'])
        self.assertGreater(result['timeout_probability'],0)
        self.assertLess(result['timeout_probability'],1e-30)
        self.assertEqual(result['branch_checks'][0]['primary_conditional_status'],'checked')
        self.assertEqual(result['branch_checks'][0]['independent_conditional_status'],'checked')

    def test_rare_timeout_reset_fails_even_when_absolute_residual_passes(self):
        r=next(fixtures());p=.9;n=32;q=compile_early_measure(r.target,p,n)
        with q.if_test((q.clbits[0],False)):q.reset(1)
        result=self.verify_circuit(q,r.target,p,n)
        self.assertLess(result['success_residual'],1e-9)
        self.assertLess(result['timeout_residual'],1e-9)
        self.assertFalse(result['verified'])
        for engine in ('primary','independent'):
            self.assertIn(('CONDITIONAL_STATE_MISMATCH','timeout',engine),self.reasons(result))
            self.assertGreater(result[engine+'_timeout_conditional_residual'],.1)

    def test_erased_rare_timeout_reports_missing_branch(self):
        r=next(fixtures());p=.9;n=32;q=compile_early_measure(r.target,p,n)
        with q.if_test((q.clbits[0],False)):
            q.x(2);q.measure(2,0)
        result=self.verify_circuit(q,r.target,p,n)
        self.assertFalse(result['verified'])
        self.assertIn(('MISSING_BRANCH','timeout','primary'),self.reasons(result))
        self.assertIn(('BRANCH_PROBABILITY_MISMATCH','timeout','independent'),self.reasons(result))

    def test_wrong_retry_cap_reports_probability_mismatch(self):
        r=next(fixtures());result=self.verify_circuit(compile_early_measure(r.target,.625,1),r.target,.625,2)
        self.assertFalse(result['verified'])
        self.assertIn(('BRANCH_PROBABILITY_MISMATCH','timeout','primary'),self.reasons(result))
        self.assertLess(result['primary_timeout_conditional_residual'],1e-9)

    def test_basis_preserving_phase_error_detected_on_success(self):
        # Z preserves computational basis outputs as rays but damages superpositions.
        q=compile_deterministic(np.eye(2));q.z(1)
        result=self.verify_circuit(q,np.eye(2),1,1)
        self.assertFalse(result['verified'])
        self.assertIn(('CONDITIONAL_STATE_MISMATCH','success','independent'),self.reasons(result))

    def test_controlled_relative_phase_error_detected(self):
        r=next(fixtures());result=self.verify_circuit(compile_deterministic(-r.target),r.target,1,1)
        self.assertFalse(result['verified'])
        self.assertIn(('CONDITIONAL_STATE_MISMATCH','success','primary'),self.reasons(result))

    def test_zero_timeout_not_conditionally_normalized(self):
        r=next(fixtures());result=self.verify_circuit(compile_deterministic(r.target),r.target,1,1)
        self.assertTrue(result['verified'])
        self.assertEqual(result['branch_checks'][0]['primary_conditional_status'],'zero_expected_absolute_check_only')
        self.assertNotIn('primary_timeout_conditional_residual',result)

    def test_too_small_branch_explicitly_unresolved(self):
        identity=ideal_choi(np.eye(2));outputs=[1e-280*identity,identity]
        result=compare_branches(outputs,outputs,np.eye(2),1,1e-280)
        self.assertFalse(result['verified'])
        self.assertEqual(result['branch_checks'][0]['primary_conditional_status'],'below_resolution')
        self.assertIn(('UNRESOLVED_RARE_BRANCH','timeout','independent'),self.reasons(result))

    def test_independent_engine_fault_is_detected(self):
        real=independent.local_gate
        def faulty(name,params):
            return np.eye(2) if name=='x' else real(name,params)
        r=next(fixtures())
        with patch('retryguard.independent.local_gate',side_effect=faulty):
            result=self.verify_circuit(compile_deterministic(r.target),r.target,1,1)
        self.assertFalse(result['verified'])
        self.assertLess(result['success_residual'],1e-9)
        self.assertIn(('UNEXPECTED_BRANCH','timeout','independent'),self.reasons(result))

    def test_independent_primitives_known_answers(self):
        self.assertTrue(np.allclose(independent.local_gate('u',[np.pi,0,np.pi]),[[0,1],[1,0]]))
        cx=independent.embed(independent.local_gate('cx',[]),[0,2],3)
        for value in range(8):
            expected=value ^ (4 if value&1 else 0)
            self.assertEqual(np.argmax(abs(cx[:,value])),expected)
        bell=independent.seed(1,[0])
        self.assertTrue(np.allclose(independent.partial_trace(bell,[0]),np.eye(2)/2))
        q=QuantumCircuit(1);q.reset(0)
        result=independent.execute(q,bell)[()]
        expected=np.zeros((4,4));expected[0,0]=.5;expected[2,2]=.5
        self.assertTrue(np.allclose(result,expected))
        measured=QuantumCircuit(1,1);measured.measure(0,0)
        states=independent.execute(measured,bell)
        self.assertAlmostEqual(np.trace(states[(0,)]).real,.5)
        self.assertAlmostEqual(np.trace(states[(1,)]).real,.5)
        self.assertAlmostEqual(states[(1,)][3,3].real,.5)

    def test_independent_rejects_unknown_gate(self):
        with self.assertRaisesRegex(InputError,'Second verifier'):
            independent.local_gate('imaginary_gate',[])

    def test_source_rare_timeout_cross_checked(self):
        r=list(fixtures())[2];p=analyze(r)['p'];n=32
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'source.qasm';save_qasm(compile_source_retry(r,n),path)
            result=verify_source_retry(path,r.target,1-(1-p)**n,timeout_probability=(1-p)**n)
        self.assertTrue(result['verified'],result['failures'])
        self.assertLess(result['timeout_probability'],1e-20)
        self.assertGreater(result['timeout_probability'],0)

    def test_probability_contract_consistency(self):
        r=next(fixtures())
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'c.qasm';save_qasm(compile_deterministic(r.target),path)
            with self.assertRaisesRegex(InputError,'sum to one'):
                verify(path,r.target,.9,timeout_probability=.2)

    def test_omitted_rare_timeout_does_not_silently_certify(self):
        r=next(fixtures());q=compile_early_measure(r.target,.9,32)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'c.qasm';save_qasm(q,path)
            result=verify(path,r.target,1.0)
        self.assertFalse(result['verified'])
        self.assertIn(('UNRESOLVED_UNEXPECTED_BRANCH','timeout','primary'),self.reasons(result))

    def test_cli_gate_keeps_branch_failure_reasons(self):
        from retryguard.__main__ import require_verified
        r=next(fixtures());q=compile_early_measure(r.target,.9,32)
        with q.if_test((q.clbits[0],False)):q.reset(1)
        result=self.verify_circuit(q,r.target,.9,32)
        with self.assertRaises(InputError) as caught:
            require_verified(result)
        error=caught.exception.as_dict()
        self.assertEqual(error['code'],'VERIFICATION_FAILED')
        self.assertIn('timeout: CONDITIONAL_STATE_MISMATCH',error['message'])
        self.assertTrue(error['details'])
