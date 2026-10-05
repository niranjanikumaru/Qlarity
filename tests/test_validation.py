"""Boundary checks and integration tests for partial/all-rejected batches."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from qiskit import QuantumCircuit, qasm3
from qiskit.circuit import Parameter
from retryguard.analysis import analyze, retry_cap
from retryguard.compiler import compile_early_measure
from retryguard.fixtures import Routine, fixtures, manifest_entries
from retryguard.validation import InputError, numeric_matrix, validate_trial
from retryguard.__main__ import main


class Validation(unittest.TestCase):
    def assert_code(self, code, fn):
        with self.assertRaises(InputError) as caught:
            fn()
        self.assertEqual(caught.exception.code, code)
        self.assertTrue(caught.exception.field)

    def test_nonfinite_and_malformed_target(self):
        r = next(fixtures())
        for target, code in [(np.full((2, 2), np.nan), 'NONFINITE_MATRIX'),
            (np.full((2, 2), np.inf), 'NONFINITE_MATRIX'),
            (np.eye(3), 'INVALID_MATRIX'), ([[1, 0], [0]], 'INVALID_MATRIX'),
            ([['1', '0'], ['0', '1']], 'INVALID_MATRIX'),
            ([[True, 0], [0, 1]], 'INVALID_MATRIX'),
            (np.full((2, 2), 1e308), 'NONUNITARY_TARGET')]:
            with self.subTest(code=code, target=repr(target)):
                bad = Routine('bad', r.trial, target, 'test', 'test', '')
                self.assert_code(code, lambda: analyze(bad))
        self.assert_code('INVALID_MATRIX', lambda: numeric_matrix([[1+1j,0],[0,1]], 'target_real', True))

    def test_probability_and_budget_boundaries(self):
        for p in (-.1, 0, 1.1):
            self.assert_code('INVALID_PROBABILITY', lambda: retry_cap(p, .01, 16))
        for p in (np.nan, np.inf, True, '0.5'):
            self.assert_code('INVALID_NUMBER', lambda: retry_cap(p, .01, 16))
        for epsilon in (-1, 0, 1, 2):
            self.assert_code('INVALID_TIMEOUT', lambda: retry_cap(.5, epsilon, 16))
        for epsilon in (np.nan, np.inf, True):
            self.assert_code('INVALID_NUMBER', lambda: retry_cap(.5, epsilon, 16))
        for cap in (0, 33, True, 2.5):
            self.assert_code('INVALID_CAP', lambda: retry_cap(.5, .01, cap))
        self.assert_code('INFEASIBLE_BUDGET', lambda: retry_cap(.5, .01, 2))
        self.assertEqual(retry_cap(1, .01, 1), 1)
        self.assert_code('INVALID_NUMBER', lambda: compile_early_measure(np.eye(2), np.nan, 2))

    def test_unsupported_circuits_and_parameters(self):
        reset = QuantumCircuit(2); reset.reset(0)
        delay = QuantumCircuit(2); delay.delay(1, 0)
        measured = QuantumCircuit(2, 1); measured.measure(0, 0)
        unbound = QuantumCircuit(2); unbound.ry(Parameter('theta'), 0)
        infinite = QuantumCircuit(2); infinite.ry(float('inf'), 0)
        for q, code in [(reset, 'UNSUPPORTED_OPERATION'), (delay, 'UNSUPPORTED_OPERATION'),
            (measured, 'UNSUPPORTED_CLASSICAL_BITS'), (unbound, 'UNBOUND_PARAMETERS'),
            (infinite, 'NONFINITE_GATE'), (QuantumCircuit(4), 'UNSUPPORTED_QUBITS')]:
            with self.subTest(code=code):
                self.assert_code(code, lambda: validate_trial(q))

    def write_fixture(self, root):
        r = next(fixtures())
        (root/'trial.qasm').write_text(qasm3.dumps(r.trial))
        return {'name': 'valid', 'qasm': 'trial.qasm', 'target_real': r.target.real.tolist(),
            'target_imag': r.target.imag.tolist(), 'source': 'test', 'lineage': 'test'}

    def run_cli(self, argv):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch('sys.argv', ['retryguard', *argv]), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main()
        return code, stdout.getvalue(), stderr.getvalue()

    def test_mixed_batch_keeps_valid_items_on_both_sides(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); valid = self.write_fixture(root)
            nonfinite = dict(valid, name='nan_target', target_real=[[float('nan'),0],[0,1]])
            missing = dict(valid, name='missing'); del missing['target_imag']
            after = dict(valid, name='after')
            path = root/'manifest.json'; path.write_text(json.dumps([valid, nonfinite, missing, after]))
            code, stdout, stderr = self.run_cli(['--manifest', str(path), '--out', str(root/'out')])
            self.assertEqual(code, 1)
            report = json.loads((root/'out/benchmark.json').read_text())
            self.assertEqual(report['summary']['items_accepted'], 2)
            self.assertEqual(report['summary']['items_rejected'], 2)
            self.assertFalse(report['summary']['all_verified'])
            self.assertEqual([x['code'] for x in report['errors']], ['NONFINITE_MATRIX', 'MISSING_FIELD'])
            self.assertEqual(len(report['results']), 8)
            for row in report['results']+report['source_retry_results']:
                self.assertTrue((root/'out'/row['qasm_file']).is_file())
            self.assertIn('NONFINITE_MATRIX', stderr)
            self.assertNotIn('Traceback', stderr)

    def test_item_schema_paths_parse_and_duplicate_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); v = self.write_fixture(root)
            (root/'broken.qasm').write_text('not qasm')
            cases = [(3, 'MANIFEST_ITEM'), (dict(v, name='bad-name'), 'INVALID_NAME'),
                (dict(v, surprise=True), 'UNKNOWN_FIELD'), (dict(v, source=None), 'INVALID_FIELD'),
                (dict(v, note=2), 'INVALID_FIELD'), (dict(v, qasm='../outside.qasm'), 'QASM_PATH'),
                (dict(v, qasm='bad\x00path'), 'QASM_PATH'), (dict(v, qasm='absent.qasm'), 'QASM_READ'), (dict(v, qasm='broken.qasm'), 'QASM_PARSE')]
            path = root/'m.json'
            for item, code in cases:
                with self.subTest(code=code):
                    path.write_text(json.dumps([item]))
                    entry = list(manifest_entries(path))[0]
                    self.assertEqual(entry[3].code, code)
            path.write_text(json.dumps([v, v, dict(v, name='last')]))
            entries = list(manifest_entries(path))
            self.assertEqual([e[3].code for e in entries[:2]], ['DUPLICATE_NAME', 'DUPLICATE_NAME'])
            self.assertIsNotNone(entries[2][2])

    def test_all_rejected_reports_and_no_stale_artifact_references(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); v = self.write_fixture(root); path = root/'m.json'
            path.write_text(json.dumps([v]))
            self.assertEqual(self.run_cli(['--manifest', str(path), '--out', str(root/'out')])[0], 0)
            path.write_text(json.dumps([dict(v, target_real=[[float('inf'),0],[0,1]])]))
            code, _, _ = self.run_cli(['--manifest', str(path), '--out', str(root/'out')])
            self.assertEqual(code, 1)
            report = json.loads((root/'out/benchmark.json').read_text())
            self.assertEqual(report['results'], [])
            self.assertEqual(report['source_retry_results'], [])
            self.assertEqual(report['summary']['status'], 'rejected')
            self.assertTrue((root/'out/errors.json').is_file())
            self.assertEqual(len((root/'out/benchmark.csv').read_text().splitlines()), 1)

    def test_invalid_global_request_does_not_start_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = root/'m.json'
            for text, expected in [('{', 'MANIFEST_JSON'), ('{}', 'MANIFEST_ROOT'), ('[]', 'MANIFEST_ROOT'),
                ('[{"name":"a","name":"b"}]', 'DUPLICATE_JSON_KEY')]:
                path.write_text(text)
                code, _, stderr = self.run_cli(['--manifest', str(path), '--out', str(root/'out')])
                self.assertEqual(code, 2); self.assertIn(expected, stderr)
                self.assertFalse((root/'out').exists())
            code, _, stderr = self.run_cli(['--timeout', 'nan', '--out', str(root/'out')])
            self.assertEqual(code, 2); self.assertIn('INVALID_NUMBER', stderr)
            self.assertFalse((root/'out').exists())

    def test_fixed_baseline_infeasible_does_not_block_selected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); v = self.write_fixture(root); path = root/'m.json'
            path.write_text(json.dumps([v]))
            code, _, _ = self.run_cli(['--manifest', str(path), '--max-attempts', '5', '--out', str(root/'out')])
            self.assertEqual(code, 0)
            report = json.loads((root/'out/benchmark.json').read_text())
            self.assertEqual({r['policy'] for r in report['results']}, {'selected_early_measure', 'deterministic'})
            self.assertEqual({r['policy'] for r in report['source_retry_results']}, {'source_selected'})
            self.assertEqual(len(report['items'][0]['unavailable_policies']), 3)

    def test_low_success_probability_supported_without_fixed_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); q = QuantumCircuit(2)
            q.ry(2*np.arccos(np.sqrt(.25)), 0)
            (root/'trial.qasm').write_text(qasm3.dumps(q))
            v = {'name':'low_p','qasm':'trial.qasm','target_real':np.eye(2).tolist(),
                'target_imag':np.zeros((2,2)).tolist(),'source':'test','lineage':'test'}
            path = root/'m.json';path.write_text(json.dumps([v]))
            code, _, _ = self.run_cli(['--manifest', str(path), '--max-attempts', '17', '--out', str(root/'out')])
            self.assertEqual(code, 0)
            report = json.loads((root/'out/benchmark.json').read_text())
            self.assertEqual(report['source_retry_results'][0]['cap'], 17)
            self.assertEqual(report['items'][0]['unavailable_policies'][0]['code'], 'BASELINE_DOMAIN')

    def test_generation_failure_isolated_and_partial_files_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); v = self.write_fixture(root); path=root/'m.json'
            path.write_text(json.dumps([v, dict(v, name='second')]))
            from retryguard.__main__ import generate
            def failing(routine, args, out, gen):
                if routine.name == 'valid':
                    (gen/'partial.qasm').write_text('partial')
                    raise RuntimeError('injected compiler failure')
                return generate(routine, args, out, gen)
            with patch('retryguard.__main__.generate', side_effect=failing):
                code, _, stderr = self.run_cli(['--manifest',str(path),'--out',str(root/'out')])
            self.assertEqual(code, 1)
            self.assertIn('PROCESSING_ERROR',stderr)
            self.assertEqual(list((root/'out').rglob('partial.qasm')), [])
            report=json.loads((root/'out/benchmark.json').read_text())
            self.assertEqual(report['summary']['items_accepted'],1)

    def test_no_feasible_retry_still_reports_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); v=self.write_fixture(root); path=root/'m.json'
            path.write_text(json.dumps([v]))
            code, _, _ = self.run_cli(['--manifest',str(path),'--max-attempts','1','--out',str(root/'out')])
            self.assertEqual(code,0)
            report=json.loads((root/'out/benchmark.json').read_text())
            self.assertEqual([r['policy'] for r in report['results']],['deterministic'])
            self.assertEqual(report['source_retry_results'],[])
            self.assertEqual(len(report['items'][0]['unavailable_policies']),5)
