"""Full-program source retry contracts, checked after QASM export/import."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from qiskit import QuantumCircuit
from retryguard.analysis import analyze
from retryguard.compiler import compile_source_retry, corrected_source, save_qasm, static_counts
from retryguard.fixtures import fixtures, Routine, X
from retryguard.verifier import verify_source_retry


class SourceRetryContracts(unittest.TestCase):
    def check_export(self, circuit, routine, cap):
        p = analyze(routine)['p']
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'source.qasm'
            save_qasm(circuit, path)
            return verify_source_retry(path, routine.target, 1-(1-p)**cap, timeout_probability=(1-p)**cap)

    def assert_valid(self, check):
        for name in ('success_residual', 'timeout_residual', 'trace_residual'):
            self.assertTrue(np.isfinite(check[name]))
            self.assertLess(check[name], 1e-9, name)

    def test_all_sources_multiple_caps_roundtrip(self):
        for routine in fixtures():
            for cap in (1, 2, 5, 7, 32):
                with self.subTest(routine=routine.name, cap=cap):
                    q = compile_source_retry(routine, cap)
                    check = self.check_export(q, routine, cap)
                    self.assert_valid(check)
                    self.assertAlmostEqual(check['timeout_probability'], (1-analyze(routine)['p'])**cap, places=9)
                    # These are static counts, including branches skipped at runtime.
                    counts = static_counts(q)
                    a = routine.trial.num_qubits - 1
                    self.assertEqual(counts['measure'], cap*a)
                    self.assertEqual(counts['reset'], (cap-1)*a)

    def test_success_stops_before_second_trial(self):
        trial = QuantumCircuit(2)
        trial.x(1)
        routine = Routine('certain_x', trial, X, 'test', 'synthetic', '')
        for cap in (2, 5):
            self.assert_valid(self.check_export(compile_source_retry(routine, cap), routine, cap))
        # X twice is identity: this must fail if successful attempts are repeated.
        bad = corrected_source(routine, analyze(routine))
        bad.compose(corrected_source(routine, analyze(routine)), inplace=True)
        self.assertGreater(self.check_export(bad, routine, 2)['success_residual'], .5)

    def mutated_loop(self, routine, *, final_recovery=True, reset_ancillas=True):
        a = routine.trial.num_qubits-1
        analysis = analyze(routine)
        q = corrected_source(routine, analysis)
        retry = QuantumCircuit(a+1, a)
        if reset_ancillas:
            retry.reset(range(a))
        retry.compose(corrected_source(routine, analysis, final_recovery), inplace=True)
        q.if_else((q.cregs[0], 0), QuantumCircuit(a+1, a), retry, q.qubits, q.clbits)
        return q

    def test_missing_final_recovery_is_detected(self):
        for routine in fixtures():
            with self.subTest(routine=routine.name):
                check = self.check_export(self.mutated_loop(routine, final_recovery=False), routine, 2)
                self.assertLess(check['success_residual'], 1e-9)
                self.assertGreater(check['timeout_residual'], .001)

    def test_missing_ancilla_reset_is_detected(self):
        routine = next(fixtures())
        check = self.check_export(self.mutated_loop(routine, reset_ancillas=False), routine, 2)
        self.assertGreater(max(check['success_residual'], check['timeout_residual']), .001)

    def test_invalid_caps_rejected(self):
        routine = next(fixtures())
        for cap in (0, 33, -1, 1.5, True):
            with self.subTest(cap=cap), self.assertRaises(ValueError):
                compile_source_retry(routine, cap)

    def test_cli_includes_separate_source_contract_and_artifacts(self):
        from retryguard.__main__ import main
        with tempfile.TemporaryDirectory() as directory:
            with patch('sys.argv', ['retryguard', '--out', directory]), contextlib.redirect_stdout(io.StringIO()):
                main()
            report = json.loads((Path(directory)/'benchmark.json').read_text())
            self.assertEqual(len(report['source_retry_results']), 6)
            self.assertEqual(len(report['results']), 12)
            for row in report['source_retry_results']:
                self.assertTrue(row['verified'])
                self.assertTrue((Path(directory)/row['qasm_file']).is_file())
            self.assertTrue((Path(directory)/'source_retry.json').is_file())


if __name__ == '__main__':
    unittest.main()
