import copy
import tempfile
import unittest
from pathlib import Path
import numpy as np
from qiskit import QuantumCircuit
from retryguard.fixtures import Routine, fixtures
from retryguard.selection import compare, rank, DEFAULT_WEIGHTS, validate_weights
from retryguard.validation import InputError
from evaluation.run_evaluation import frozen_check

class Selection(unittest.TestCase):
    def run_comparison(self,r,**kwargs):
        with tempfile.TemporaryDirectory() as d:return compare(r,Path(d),**kwargs)

    def test_deterministic_wins_real_verified_case(self):
        report=self.run_comparison(next(fixtures()))
        self.assertEqual(report['recommendation']['policy'],'deterministic')
        self.assertTrue(all(c['verified'] for c in report['candidates']))
        self.assertEqual(len(report['candidates']),4)
        self.assertEqual(frozen_check()['core_files_unchanged'],7)

    def test_source_constraint_changes_winner(self):
        report=self.run_comparison(next(fixtures()),require_source=True)
        self.assertEqual(report['recommendation']['policy'],'repaired_source')
        self.assertFalse(report['candidates'][-1]['eligible'])

    def test_infeasible_retry_budget_keeps_deterministic(self):
        report=self.run_comparison(next(fixtures()),max_attempts=1)
        self.assertEqual(report['recommendation']['policy'],'deterministic')
        self.assertEqual(sum(c['eligible'] for c in report['candidates']),1)
        report=self.run_comparison(next(fixtures()),max_attempts=1,require_source=True)
        self.assertIsNone(report['recommendation']['policy'])

    def test_costs_include_final_failure_recovery_and_pre_retry_reset(self):
        q=QuantumCircuit(2);q.ry(np.pi/2,0);q.cx(0,1)
        r=Routine('counting',q,np.eye(2),'test','test','Hand-calculated p=1/2 instrument')
        report=self.run_comparison(r,timeout=.25,max_attempts=2)
        c=report['candidates'][0]
        self.assertEqual(c['cap'],2)
        expected={'cx':1.5,'one_qubit':2.25,'measure':1.5,'reset':.5}
        for key,value in expected.items():self.assertAlmostEqual(c['expected_counts'][key],value)
        self.assertTrue(c['verified'])

    def test_unverified_or_over_budget_never_wins(self):
        def candidate(name,cost,verified=True,timeout=0.):
            return dict(policy=name,verified=verified,timeout_probability=timeout,preserves_source=True,
                        expected_counts={'cx':0,'one_qubit':cost,'measure':0,'reset':0},qasm_file=name+'.qasm')
        candidates=[candidate('broken',0,False),candidate('too_risky',0,True,.2),candidate('valid',3)]
        self.assertEqual(rank(candidates,DEFAULT_WEIGHTS,.01)['policy'],'valid')

    def test_weights_can_change_choice_without_policy_bias(self):
        a=dict(policy='deterministic',verified=True,timeout_probability=0.,preserves_source=False,qasm_file='a',expected_counts={'cx':2,'one_qubit':1,'measure':0,'reset':0})
        b=dict(policy='selected_retry',verified=True,timeout_probability=.005,preserves_source=False,qasm_file='b',expected_counts={'cx':0,'one_qubit':8,'measure':0,'reset':0})
        self.assertEqual(rank(copy.deepcopy([a,b]),DEFAULT_WEIGHTS,.01)['policy'],'selected_retry')
        w={**DEFAULT_WEIGHTS,'cx':0.}
        self.assertEqual(rank(copy.deepcopy([a,b]),w,.01)['policy'],'deterministic')

    def test_invalid_weights(self):
        for value in (-1,float('nan'),float('inf'),True):
            with self.assertRaises(InputError):validate_weights({**DEFAULT_WEIGHTS,'cx':value})
        with self.assertRaises(InputError):validate_weights(dict.fromkeys(DEFAULT_WEIGHTS,0))

    def test_fixed_domain_unavailable_but_selected_still_valid(self):
        q=QuantumCircuit(2);q.ry(2*np.arccos(np.sqrt(.25)),0)
        r=Routine('low_p',q,np.eye(2),'test','test','p=1/4')
        report=self.run_comparison(r,timeout=.5,max_attempts=4)
        self.assertFalse(report['candidates'][1]['eligible'])
        self.assertTrue(report['candidates'][2]['verified'])
        self.assertEqual(report['candidates'][2]['cap'],3)
