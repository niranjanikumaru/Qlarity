# Interactive execution report

Requires Python 3.12+ and the project dependencies. From the extracted `retryguard` folder:

```sh
python -m pip install -r requirements.txt
python -m retryguard.web
```

Open http://127.0.0.1:8765 in your browser. Stop with Ctrl+C. Use `--port 8766` if needed. Runs are saved in `web_runs/`; use `--runs PATH` to change the location.

1. Choose IBM rotation, Guppy V3 or gearbox, or upload a one-item manifest and gate-only OpenQASM 3 file. The manifest uses the same fields as the CLI. The uploaded QASM replaces the manifest's filename; the server does not read a client-supplied path.
2. Set timeout probability and maximum attempts; optionally require source preservation or adjust the displayed cost weights.
3. Run analysis. The backend validates input, diagnoses original branches, generates four alternatives, checks exported circuits with both numerical engines, and compares eligible candidates.
4. Read the original failure explanation, affected-state example and proposed correction. This diagnosis describes the original trial, not an upstream bug claim. Successful exported-program verification is reported separately in the comparison.
5. Download verified QASM, the full JSON execution report, or a ZIP containing the request, report and verified circuits. Ineligible but verified circuits are clearly distinguished in the comparison.

Results are created by execution, not loaded from packaged benchmark reports. A request hash and run ID identify the evidence. Changing input clears visible results; an in-flight older result is discarded by the interface. Repair, verification and comparison share one execution stage because the existing selector generates and checks each candidate together; the UI does not invent progress percentages or premature passes.

This is a local, single-user prototype. It binds to loopback, processes one run at a time, enforces upload limits, and terminates an execution after 120 seconds. It is not a public multi-user hosting service. Uploads and reports stay in the selected local run directory; delete that directory when no longer needed. The Python process must remain running while the page is used. No external frontend services or CDNs are needed.

Scope: ideal continuous U/CX, one data qubit, at most two source ancillas, caps up to 32. Comparisons use the uncontrolled target contract, not controlled-source repair. Costs are illustrative operation weights; no hardware benefit or proof of formal correctness is claimed. The frozen analyzer, compiler and verifier files are unchanged.
