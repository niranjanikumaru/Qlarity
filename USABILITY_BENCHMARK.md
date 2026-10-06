# Measurable Advantage Usability Benchmark

To establish a defensible claim of advantage for Round 1 judging, we must demonstrate that RetryGuard actually saves developers time and prevents errors compared to standard manual workflows.

**Instructions for the Team Lead:**
Provide this benchmark guide to 3 teammates who were not involved in building the RetryGuard core. Ensure you use an environment with Python 3.12+ and `qiskit` installed.

## 1. Setup
*   **The Goal:** Repair small, probabilistic quantum subroutines (RUS or conditional logic) to satisfy strict timeout/retry limits without losing data.
*   **The Baseline:** Writing manual Qiskit Python scripts to verify unnormalized Choi maps and insert corrective gates.
*   **The Tool:** The RetryGuard `retryguard` CLI.

## 2. The Tasks
Provide your teammates with 6 tasks (these can be small QASM files):
*   **3 Clean Tasks:** Correct, reversible RUS routines (e.g., standard phase-flip recovery, bit-flip recovery, and the T-injection you just wrote).
*   **3 Broken Tasks (Injected Faults):**
    *   *Fault 1:* A trial that omits the final recovery gate, resetting the data instead.
    *   *Fault 2:* A trial that applies the wrong unitary on success.
    *   *Fault 3:* An irreversible trial that fundamentally destroys input data.

## 3. The Protocol
Randomize the order: Have each teammate solve 3 tasks manually, and 3 using RetryGuard.

For each task, ask the teammate to:
1. Identify if the subroutine is safe (data is preserved on failure/timeout).
2. If safe, output a corrected circuit that loops or retries boundedly.
3. If unsafe, state the reason.

## 4. What to Measure
Record the following for each teammate and task:
*   **Time to complete** (minutes).
*   **Lines of manual specification/code written** (count).
*   **Correct completion?** (Yes/No - did their manual script accurately catch the injected timeout faults?).

## 5. Interpreting the Results
You can claim a distinct advantage if RetryGuard requires fewer manual lines of code, is consistently faster, and catches the subtle timeout reset faults (which standard debugging often misses). **Include these numbers in your hackathon submission presentation.**
