"""Contracts external to the frozen analyzer, including negative adapter cases."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from evaluation.run_evaluation import ROOT, build_adqc, evaluate, frozen_check, natural_comparator, teammate
from retryguard.analysis import analyze
from retryguard.validation import InputError

class ExternalEvaluation(unittest.TestCase):
    def test_frozen_core_and_tamper_detection(self):
        self.assertEqual(frozen_check()['core_files_unchanged'],7)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'evaluation').mkdir();(root/'core').write_text('changed')
            (root/'evaluation/baseline_freeze.json').write_text(json.dumps({'sha256':{'core':'wrong'},'frozen_contracts':{}}))
            with self.assertRaisesRegex(ValueError,'FROZEN_BASELINE_CHANGED'):frozen_check(root)

    def test_source_equations_and_raw_failure(self):
        r,s=build_adqc();a=analyze(r);x=np.array([[0,1],[1,0]])
        np.testing.assert_allclose(a['kraus'][0],r.target/np.sqrt(2),atol=1e-12)
        np.testing.assert_allclose(a['kraus'][1],x@r.target/np.sqrt(2),atol=1e-12)
        np.testing.assert_allclose(a['repairs'][0]@a['kraus'][1],np.eye(2)/np.sqrt(2),atol=1e-12)
        self.assertGreater(np.linalg.norm(a['kraus'][1]-np.eye(2)/np.sqrt(2)),.1)

    def test_caps_and_natural_feedforward(self):
        r,s=build_adqc()
        with tempfile.TemporaryDirectory() as d:
            report=evaluate(r,s,Path(d))
            self.assertTrue(report['semantic_pass']);self.assertEqual(report['selected_cap'],7)
            self.assertTrue(natural_comparator(r,Path(d))['verification']['verified'])

    def test_wrong_declared_target_rejected(self):
        r,s=build_adqc();r.target=np.eye(2,dtype=complex)
        with self.assertRaises(InputError) as caught:analyze(r)
        self.assertEqual(caught.exception.code,'TARGET_MISMATCH')

    def test_teammate_pending_and_incomplete_attestation(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)
            self.assertIsNone(teammate(None,None,out)['semantic_pass'])
            att=out/'authorship.json';att.write_text('{}')
            with self.assertRaisesRegex(ValueError,'AUTHORSHIP_FIELDS_MISSING'):teammate(out/'manifest.json',att,out)

    def test_teammate_wrong_task_rejected(self):
        build_adqc()
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);att=out/'authorship.json'
            att.write_text(json.dumps({'author':'Synthetic test identity, not a submission',
                'written_independently_of_retryguard_core':True,'core_author_involved':False,
                'ai_assistance_disclosed':'Test fixture only','source_url':'Test fixture only','notes':'Not teammate evidence'}))
            with self.assertRaisesRegex(ValueError,'TASK_FAILURE_BRANCH_MISMATCH'):
                teammate(ROOT/'evaluation/new_family/manifest.json',att,out)

    def test_synthetic_submission_never_claims_independence(self):
        # Harness test only, explicitly NOT the requested teammate artifact.
        from qiskit import QuantumCircuit
        from retryguard.fixtures import Routine
        q=QuantumCircuit(2);q.h(0);q.t(0);q.cx(1,0)
        r=Routine('synthetic_test',q,np.diag([1,np.exp(1j*np.pi/4)]),'test','test','Assistant-authored test only')
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);att=out/'authorship.json'
            att.write_text(json.dumps({'author':'Synthetic test identity, not a submission',
                'written_independently_of_retryguard_core':True,'core_author_involved':False,
                'ai_assistance_disclosed':'Assistant-authored harness test only',
                'source_url':'Test fixture only','notes':'Not teammate evidence'}))
            with patch('evaluation.run_evaluation.load_manifest',return_value=iter([r])):
                report=teammate(out/'unused.json',att,out)
            self.assertTrue(report['semantic_pass'])
            self.assertFalse(report['independence_verified'])
            self.assertEqual(report['status'],'self_attested_pending_human_review')
