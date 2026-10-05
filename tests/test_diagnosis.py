import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from qiskit import QuantumCircuit, qasm3
from scipy.linalg import null_space
from retryguard.fixtures import fixtures, Routine, I, X
from retryguard.diagnosis import diagnose_routine, input_diagnosis, render_html
from retryguard.validation import InputError
from retryguard.verifier import execute, reduce
from retryguard.compiler import corrected_source
from retryguard.analysis import analyze
from retryguard.__main__ import main


def leaking_routine():
    ks=[np.sqrt(.5)*I,np.diag([np.sqrt(.5),0]),np.diag([0,np.sqrt(.5)]),np.zeros((2,2))]
    columns=np.zeros((8,2),complex)
    for j,k in enumerate(ks): columns[[j,j+4],:]=k
    unitary=np.zeros((8,8),complex);unitary[:,[0,4]]=columns
    unitary[:,[1,2,3,5,6,7]]=null_space(columns.conj().T)
    q=QuantumCircuit(3);q.unitary(unitary,[0,1,2])
    return Routine('leaking',q,I,'synthetic','synthetic','')


class Diagnosis(unittest.TestCase):
    def test_ibm_bit_flip_witness_and_proposal(self):
        d=diagnose_routine(next(fixtures()))
        self.assertEqual(d['branches'][0]['status'],'satisfied')
        for b in d['branches'][1:]:
            self.assertEqual(b['status'],'violated')
            self.assertEqual(b['proposed_correction']['kind'],'X')
            w=b['affected_state']
            self.assertEqual(w['input_state'],'zero |0>')
            self.assertEqual(w['measurement_basis'],'Z')
            self.assertAlmostEqual(w['expected_plus_probability'],1)
            self.assertAlmostEqual(w['actual_plus_probability'],0)
            self.assertAlmostEqual(w['corrected_plus_probability'],1)
            self.assertFalse(b['correction_verified'])

    def test_witness_matches_separate_density_execution(self):
        r=next(fixtures());a=analyze(r)
        # Independently run |0> through original and recovered measured trials.
        initial=np.zeros((8,8),complex);initial[0,0]=1
        for repaired in (False,True):
            states=execute(corrected_source(r,a,repaired),initial)
            branch=states[(1,0)]
            data=reduce(branch,[2]);probability=np.trace(data).real
            self.assertAlmostEqual(probability,.125)
            self.assertAlmostEqual((data[0,0]/probability).real,1 if repaired else 0)

    def test_phase_flip_and_already_safe_failure(self):
        r=list(fixtures())[1];d=diagnose_routine(r)
        self.assertEqual(d['branches'][1]['status'],'below_tolerance')
        self.assertIsNone(d['branches'][1]['affected_state'])
        self.assertEqual(d['branches'][2]['proposed_correction']['kind'],'Z')
        self.assertEqual(d['branches'][2]['affected_state']['input_state'],'plus |+>')
        self.assertEqual(d['branches'][3]['status'],'satisfied')
        self.assertEqual(d['branches'][3]['proposed_correction']['kind'],'identity')

    def test_irreversible_failure_has_no_proposed_unitary(self):
        d=diagnose_routine(leaking_routine())
        for b in d['branches'][1:3]:
            self.assertEqual(b['proposed_correction']['kind'],'not_repairable')
            self.assertIsNone(b['probability'])
            self.assertGreater(b['probability_witness']['high_probability']-b['probability_witness']['low_probability'],.4)
            self.assertNotIn('corrected_plus_probability',b['affected_state'])

    def test_success_target_mismatch_is_not_timeout_error(self):
        q=QuantumCircuit(2);q.x(1)
        d=diagnose_routine(Routine('wrong',q,I,'test','test',''))
        b=d['branches'][0]
        self.assertEqual(b['contract'],'success_target')
        self.assertEqual(b['status'],'violated')
        self.assertEqual(b['proposed_correction']['kind'],'review_target')
        self.assertAlmostEqual(b['affected_state']['measurement_gap'],1)

    def test_phase_only_change_is_not_false_failure(self):
        q=QuantumCircuit(2);q.h(0);q.global_phase=.7
        d=diagnose_routine(Routine('identity',q,I,'test','test',''))
        self.assertEqual([b['status'] for b in d['branches']],['satisfied','satisfied'])
        self.assertEqual(d['branches'][1]['proposed_correction']['kind'],'identity')

    def test_html_escapes_input_errors_and_does_not_invent_state(self):
        d=input_diagnosis('<script>bad</script>',InputError('BAD','<img src=x onerror=bad>','target'))
        page=render_html([d])
        self.assertNotIn('<script>',page);self.assertNotIn('<img',page)
        self.assertIn('&lt;script&gt;',page)
        self.assertEqual(d['branches'],[])
        self.assertIn('No affected quantum state',page)

    def test_cli_keeps_rejected_branch_diagnosis_and_links_verified_repairs(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);items=[]
            for r in [next(fixtures()),leaking_routine()]:
                (root/(r.name+'.qasm')).write_text(qasm3.dumps(r.trial))
                items.append({'name':r.name,'qasm':r.name+'.qasm','target_real':r.target.real.tolist(),
                    'target_imag':r.target.imag.tolist(),'source':'synthetic test','lineage':'test'})
            (root/'m.json').write_text(json.dumps(items))
            with patch('sys.argv',['retryguard','--manifest',str(root/'m.json'),'--out',str(root/'out')]),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                code=main()
            self.assertEqual(code,1)
            ds=json.loads((root/'out/diagnostics.json').read_text())['items']
            self.assertEqual(ds[0]['batch_status'],'accepted')
            self.assertTrue(ds[0]['branches'][1]['correction_verified'])
            for artifact in ds[0]['verified_artifacts']:
                self.assertTrue((root/'out'/artifact['qasm_file']).is_file())
            self.assertEqual(ds[1]['batch_error']['code'],'IRREVERSIBLE_FAILURE')
            self.assertEqual(ds[1]['branches'][1]['proposed_correction']['kind'],'not_repairable')
            self.assertEqual(ds[1]['verified_artifacts'],[])
            self.assertTrue((root/'out/diagnostics.html').is_file())
