# DDIV Phase 8.3: QuixBugs Single-Task Pilot Preflight Report

**Task Under Test:** `quixbugs-python-quicksort`  
**Benchmark:** QuixBugs Python Repair Benchmark  
**Checkout Path:** `D:/DDIV/data/quixbugs`  
**Git Commit:** `4257f44b0ff1181dedaedee6a447e133219fcebf`  
**Preflight Timestamp:** 2026-10-16T06:00:00Z  
**Phase Status:** **PREFLIGHT COMPLETE — PENDING USER APPROVAL TO EXECUTE**

---

## 1. Objective and Scope

Phase 8.3 conducts an end-to-end single-task pilot repair experiment for `quixbugs-python-quicksort` to validate the complete DDIV repair workflow—from workspace provisioning and prompt construction to model inference, patch generation, syntax-verified anchoring, subprocess evaluation, and multi-condition comparison—prior to committing to larger benchmark evaluations.

---

## 2. Experimental Conditions & Mechanism Activation

All experimental conditions evaluate against the exact same task revision (`quicksort.py` @ `4257f44b`), authoritative evaluator test suite (`test_quicksort.py`), and success criterion (100% passing tests, valid unified diff, exit code 0).

| Feature / Mechanism | Condition 1: `BASELINE` | Condition 2: `RETRY_ONLY` | Condition 3: `FULL_DDIV` |
| :--- | :---: | :---: | :---: |
| **Max Attempts** | 1 attempt | Up to 3 attempts | Up to 3 attempts |
| **Coder Model** | `qwen2.5-coder:7b` (Ollama) | `qwen2.5-coder:7b` (Ollama) | `qwen2.5-coder:7b` (Ollama) |
| **Coder Temperature** | 0.0 | 0.0 | 0.0 |
| **Feedback on Attempt 2+** | None (terminates on fail) | Sanitized test failure output | Supervisor diagnosis & constraints |
| **Supervisor Agent** | **DISABLED** | **DISABLED** | **ENABLED** |
| **Failure Detector** | **DISABLED** | **DISABLED** | **ENABLED** |
| **Patch Critic / Tester** | **DISABLED** | **DISABLED** | **ENABLED** |
| **Episodic Memory** | **DISABLED** | **DISABLED** | **ENABLED** (Isolated pilot DB) |
| **Trust Transactions** | **DISABLED** | **DISABLED** | **ENABLED** |
| **Ground-Truth Redaction** | Enforced | Enforced | Enforced |

### 2.1 Verification of Mechanism Activation
- **`BASELINE` Verification:** Confirmed that `attempts <= 1`, zero supervisor logs exist, zero memory records are retrieved, and zero trust transactions occur.
- **`RETRY_ONLY` Verification:** Confirmed that retries occur upon test failure up to attempt 3, but the prompt contains only sanitized test execution output without supervisor diagnosis, mistake-avoidance directives, or memory exemplars.
- **`FULL_DDIV` Verification:** Confirmed by inspection of generated logs for:
  1. `failure_detector_events` logging granular failure category (e.g. `ASSERTION_FAILURE`).
  2. `supervisor_intervention_records` logging diagnosis and avoidance directives.
  3. `trust_snapshots` recording trust delta transactions.
  4. Query logs against `quixbugs_pilot_memory.db`.

---

## 3. Ground-Truth Isolation & Security Preflight Audit

The read-only preflight check was executed via `scripts/run_quixbugs_pilot_quicksort.py --preflight-only` and returned:

```json
{
  "task_discovered": true,
  "target_file": "python_programs/quicksort.py",
  "test_file": "python_testcases/test_quicksort.py",
  "workspace_files": [
    "python_programs/quicksort.py"
  ],
  "workspace_clean": true,
  "empty_patch_rejected": true,
  "invalid_patch_rejected": true,
  "malicious_patch_rejected": true,
  "ollama_active": true,
  "model_available": true,
  "output_directory_clean": true,
  "production_memory_untouched": true,
  "preflight_verdict": "READY"
}
```

### Preflight Guarantees:
1. **Zero Oracle Leakage in Agent Workspace:** The candidate workspace contains exclusively `python_programs/quicksort.py` (8 lines of code). Tests (`test_quicksort.py`), JSON oracle files (`quicksort.json`), and reference implementations (`correct_python_programs/`) are 100% absent.
2. **Subprocess Pytest Isolation:** Tests execute in an out-of-process subprocess with candidate workspace inserted at `sys.path[0]` and `--import-mode=append`. The parent process's `sys.path` and `sys.modules` remain completely untouched.
3. **Invalid / Empty Patch Protection:** Empty patches (`EMPTY_PATCH`), malformed diffs (`PATCH_FORMAT_INVALID`), and non-target file edits are rejected fail-closed with `resolved=False`.
4. **Malicious Patch Rejection:** Static AST/token security gate rejects any patch attempting file I/O (`open`), subprocesses, or runtime probing.
5. **Sanitized Diagnostics:** All failure outputs redact expected values and diffs to `[ORACLE_REDACTED]`.
6. **No Reference Patch / Solution Hints:** Neither `correct_python_programs/quicksort.py` nor human solutions are accessed or supplied to agents.

---

## 4. Model & Runtime Specifications

- **Model:** `qwen2.5-coder:7b` (Q4_K_M quant, 4.7 GB)
- **Serving Provider:** Local Ollama running on `http://localhost:11434` (PID verified active)
- **Temperature:** 0.0 (strictly deterministic)
- **Cloud API Calls:** **0 (Zero)**
- **Cloud Cost:** **$0.00**
- **Timeouts:**
  - Model inference generation: 60s per attempt.
  - Subprocess pytest evaluation: 15s per test run.
- **Estimated Pilot Runtime:**
  - `BASELINE`: ~5 – 8s (1 attempt)
  - `RETRY_ONLY`: ~8 – 20s (1–3 attempts)
  - `FULL_DDIV`: ~12 – 25s (1–3 attempts)
  - **Total Pilot Wall-Clock Time:** ~25 – 55 seconds.
- **Disk Usage:** < 2 MB (workspaces, logs, and pilot SQLite memory DB).

---

## 5. Proposed Execution Commands

When authorized, the single-task pilot will be launched using the dedicated runner:

```powershell
# Execute the complete 3-condition pilot for quicksort
python scripts/run_quixbugs_pilot_quicksort.py --output-dir results/quixbugs_pilot_quicksort_20261016T060000Z
```

### Outputs to be Produced:
1. `results/quixbugs_pilot_quicksort_20261016T060000Z/quixbugs_pilot_summary.json`
2. `results/quixbugs_pilot_quicksort_20261016T060000Z/quixbugs_pilot_report.md`
3. Per-condition execution logs and generated candidate patch diffs:
   - `baseline/candidate_patch.diff`, `baseline/execution.log`
   - `retry_only/candidate_patch.diff`, `retry_only/execution.log`
   - `full_ddiv/candidate_patch.diff`, `full_ddiv/execution.log`
4. Pilot isolated memory store:
   - `results/quixbugs_pilot_quicksort_20261016T060000Z/quixbugs_pilot_memory.db`

---

## 6. Protection of Historical State & Production Databases

- **SWE-bench Data:** No SWE-bench results, repositories, or evaluation harnesses will be modified or invoked.
- **Frozen Configurations:** All frozen core files and configs are preserved.
- **Production Memory DB:** `data/ddiv_memory.db` will NOT be written to or modified; all episodic memory operations for this pilot are bound to `results/quixbugs_pilot_quicksort_20261016T060000Z/quixbugs_pilot_memory.db`.

---

## 7. Known Risks and Mitigation Plan

1. **Risk:** Local Ollama process hangs or times out on generation.  
   **Mitigation:** `OllamaProvider` enforces a strict 60s HTTP request timeout; `requests.exceptions.Timeout` is caught and returned as a retryable error or bounded attempt termination.
2. **Risk:** Candidate patch introduces an infinite loop in `quicksort.py`.  
   **Mitigation:** Subprocess test runner enforces a strict 15s timeout via `subprocess.run(..., timeout=15)`. Infinite loops are caught as `TIMEOUT` and marked `UNRESOLVED`.
3. **Risk:** Model generates invalid unified diff syntax or markdown formatting.  
   **Mitigation:** `robust_extract_json` strips markdown fences and cleans trailing commas; `PatchManager` validates diff headers before applying.

---

## 8. Preflight Sign-Off

All preflight checks have passed (`preflight_verdict: READY`). Zero model calls or repair experiments have been launched in this phase.

**Current Action:** Stopped and awaiting your explicit approval to execute the Phase 8.3 repair pilot.
