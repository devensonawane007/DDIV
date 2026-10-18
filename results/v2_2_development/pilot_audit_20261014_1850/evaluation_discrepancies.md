# DDIV v2.2 Evaluation Discrepancies and Contradictions Audit

**Audit Target:** Five-Task Pilot (15 Runs) Evaluation Metric Discrepancies  
**Audit Date:** 2026-10-14  
**Audit Directory:** `results/v2_2_development/pilot_audit_20261014_1850/`

---

## 1. Discrepancy 1: Inconsistent Pass-to-Pass Denominators (0/10 vs. 0/71 and 0/10 vs. 0/84)

### 1.1 Observed Anomaly
- In `pilot_5tasks_report.md` and CSV:
  - `pydata__xarray-7393` under `RETRY_ONLY` reported P2P as `0/10`, whereas under `BASELINE` and `FULL_DDIV` it reported `0/71 (Not Run - Apply Failed)`.
  - `psf__requests-2931` under `RETRY_ONLY` reported P2P as `0/10`, whereas under `BASELINE` and `FULL_DDIV` it reported `0/84 (Not Run - Apply Failed)`.

### 1.2 Code Path & Root Cause Trace
1. **Evaluator Design Cap (`evaluation/swebench_evaluator.py:174, 259`):**
   ```python
   def evaluate_candidate_patch(..., max_p2p_tests: int = 10, ...):
       ...
       p2p_tests = record.ground_truth.pass_to_pass[:max_p2p_tests]
   ```
   To prevent hours of test suite timeouts during multi-attempt local evaluations, the Tier-1 internal evaluator explicitly caps PASS_TO_PASS execution to a subset of `max_p2p_tests` (default: 10 tests).
2. **Evaluator Execution Branching (`evaluation/swebench_evaluator.py:184-190`):**
   - If the candidate patch **fails to apply**, the evaluator immediately returns `candidate_patch_applied=False` without executing any tests. `pass_to_pass_results` is empty (`{}`).
   - If the candidate patch **successfully applies**, the evaluator executes the FAIL_TO_PASS tests and the 10-test P2P subset. `pass_to_pass_results` contains exactly 10 test result keys.
3. **Report Generation Formatter (`scripts/run_local_ollama_comparison.py:138-157` & `v2_2_recovery_manager.py:236-258`):**
   ```python
   if is_unapplied:
       p2p_t = gt_p2p  # Ground truth total from dataset (71 for Xarray, 84 for Requests)
   else:
       p2p_t = len(p2p_res)  # Count of tests actually executed (10)
   ```
4. **Resolution:**
   The apparent contradiction arose because two completely different metrics were occupying the same column denominator:
   - When the patch applied, the denominator displayed **Tests Actually Executed** (`10`).
   - When the patch failed to apply, the denominator displayed **Dataset Ground Truth Total** (`71` or `84`).
   **Correction:** Disentangle these into separate explicit columns: `GT P2P Total`, `P2P Executed`, `P2P Passed`, and `P2P Failed`.

---

## 2. Discrepancy 2: Astropy FULL_DDIV Patch Applied vs. "Not Run - Apply Failed"

### 2.1 Observed Anomaly
- In `pilot_5tasks_report.md`, `astropy__astropy-8872` under `FULL_DDIV` showed:
  - `Patch Applied: Yes`
  - `F2P Tests: 0/1 (Not Run - Apply Failed)`
  - `P2P Tests: 0/80 (Not Run - Apply Failed)`

### 2.2 Code Path & Root Cause Trace
1. **Run-Level Metric Assignment (`core/experiment_worker.py:621, 1137`):**
   ```python
   # Inside attempt loop:
   agent_apply_res = patch_mgr.apply_patch(agent_ws.path, ...)
   if agent_apply_res.is_success:
       applied_any_patch = True
   ...
   # At end of run:
   record_obj = ExperimentConditionRecord(
       patch_applied=applied_any_patch,  # Run-wide: did ANY attempt apply a patch?
       ...
   )
   ```
   In Attempt 1 of `astropy__astropy-8872` (`FULL_DDIV`), the Coder generated a patch modifying `astropy/time/tests/test_quantity_interaction.py`. This patch successfully applied to `agent_ws` (`agent_apply_success: True`). Consequently, `applied_any_patch` became `True`.
2. **Terminal Internal Evaluation (`core/experiment_worker.py:658, 1150`):**
   In Attempt 2 and Attempt 3, the Coder shifted to `astropy/units/quantity.py`, but failed to locate the anchor. Both Attempt 2 and Attempt 3 produced empty patches that failed to apply.
   At the end of the run, `internal_evaluation` recorded the outcome of the **final attempt (Attempt 3)**:
   ```json
   "internal_evaluation": {
     "verdict": "UNRESOLVED_INTERNALLY (Candidate patch application failed)"
   }
   ```
3. **Report Generation Logic:**
   The summary table pulled `patch_applied` from `record.patch_applied` (`applied_any_patch = True`), while the test counts were formatted by `FailureDisambiguator.format_test_counts(record.internal_evaluation)`, which inspected the final attempt's verdict (`Candidate patch application failed`).
4. **Resolution:**
   Disentangle run-level historical patch application from terminal candidate patch application:
   - `Patch Applied (Any Attempt): Yes`
   - `Final Candidate Patch Applied: No`
   - `Final Test Verdict: UNRESOLVED_INTERNALLY (Candidate patch application failed)`

---

## 3. Discrepancy 3: Clean-Base Environment Failure Classification

### 3.1 Observed Anomaly
- In `result_astropy__astropy-8872__baseline.json`, `result_psf__requests-2931__baseline.json`, and `result_pydata__xarray-7393__baseline.json`, the failure category was labeled as `ENVIRONMENT_FAILURE` even though the candidate patch failed to build or apply (`PATCH_BUILDER_FAILED`).

### 3.2 Code Path & Root Cause Trace
1. **Clean-Base Health Check (`evaluation/swebench_evaluator.py:379-438`):**
   Before running repair attempts, `check_clean_base_health()` executes the first 5 PASS_TO_PASS tests on the pristine repository.
   Because Tier-1 internal evaluation executes in the host environment (Windows Python 3.11) without Docker containerization:
   - Astropy (written for Python 3.7) failed pre-existing tests on Python 3.11 (`TestQuantityCreation::test_1`, etc.).
   - Requests (written for Python 2.7/3.4) failed pre-existing tests on Python 3.11 (`test_entry_points`, etc.).
   - Xarray failed pre-existing test imports due to missing compiled extensions.
   Consequently, `clean_base_health.clean_base_passed` was `False`.
2. **Failure Detector Hierarchy (`recovery/failure_detector.py:130-145`):**
   ```python
   if not clean_base_passed:
       return DetectionResult(
           candidate_failure_type=FailureType.F4,
           granular_failure_type="ENVIRONMENT_FAILURE",
           ...
       )
   ```
   `FailureDetector` prioritized `clean_base_passed == False` above patch generation and application failures!
3. **Impact on Analysis:**
   This caused runs where the Coder hallucinated file paths or anchors to be classified as `ENVIRONMENT_FAILURE` instead of `PATCH_BUILDER_FAILED` or `PATCH_APPLICATION_FAILED`.
4. **Correction:**
   Establish a strict causal priority for primary failure classification:
   1. `INFRASTRUCTURE_FAILURE` (daemon stopped / network drop)
   2. `PATCH_NOT_GENERATED` / `PATCH_BUILDER_FAILED` (syntax error, anchor not found, phantom path)
   3. `PATCH_APPLICATION_FAILED` (git apply failed)
   4. `TEST_EXECUTION_FAILURE` (F2P failed or regression on clean repo)
   5. `ENVIRONMENT_PRE_EXISTING` (only when patch successfully applied, but clean base was already broken)

---

## 4. Summary Table of Reconciled Evaluation Metrics

| Task ID | Condition | Top-Level Patch Applied | Final Patch Applied | Tests Actually Run | P2P Tested / GT Total | Verified Primary Failure Cause |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| `pylint-6903` | `BASELINE` | Yes | Yes | 1 F2P, 8 P2P | 8 / 8 | `PATCH_LOGIC_INCORRECT` (F2P failed) |
| `pylint-6903` | `RETRY_ONLY` | Yes | Yes | 1 F2P, 8 P2P | 8 / 8 | `PATCH_LOGIC_INCORRECT` (F2P failed) |
| `pylint-6903` | `FULL_DDIV` | No | No | 0 F2P, 0 P2P | 0 / 8 | `PATCH_APPLICATION_FAILED` (git apply failed) |
| `seaborn-3187` | `BASELINE` | No | No | 0 F2P, 0 P2P | 0 / 248 | `PATCH_BUILDER_FAILED` (Anchor not found) |
| `seaborn-3187` | `RETRY_ONLY` | No | No | 0 F2P, 0 P2P | 0 / 248 | `PATCH_BUILDER_FAILED` (Anchor not found) |
| `seaborn-3187` | `FULL_DDIV` | No | No | 0 F2P, 0 P2P | 0 / 248 | `PATCH_BUILDER_FAILED` (Anchor not found) |
| `xarray-7393` | `BASELINE` | No | No | 0 F2P, 0 P2P | 0 / 71 | `PATCH_BUILDER_FAILED` (Ambiguous anchor) |
| `xarray-7393` | `RETRY_ONLY` | Yes | Yes | 2 F2P, 10 P2P | 10 / 71 | `PATCH_LOGIC_INCORRECT` (F2P failed, P2P regressed) |
| `xarray-7393` | `FULL_DDIV` | No | No | 0 F2P, 0 P2P | 0 / 71 | `PATCH_APPLICATION_FAILED` (git apply failed) |
| `astropy-8872` | `BASELINE` | No | No | 0 F2P, 0 P2P | 0 / 80 | `PATCH_BUILDER_FAILED` (Phantom file path) |
| `astropy-8872` | `RETRY_ONLY` | No | No | 0 F2P, 0 P2P | 0 / 80 | `PATCH_BUILDER_FAILED` (Anchor not found) |
| `astropy-8872` | `FULL_DDIV` | **Yes (Att 1)** | **No (Att 3)** | 0 F2P, 0 P2P | 0 / 80 | `PATCH_BUILDER_FAILED` (Anchor not found in Att 3) |
| `requests-2931` | `BASELINE` | No | No | 0 F2P, 0 P2P | 0 / 84 | `PATCH_BUILDER_FAILED` (Python AST syntax error) |
| `requests-2931` | `RETRY_ONLY` | Yes | Yes | 1 F2P, 10 P2P | 10 / 84 | `PATCH_LOGIC_INCORRECT` (F2P failed, P2P regressed) |
| `requests-2931` | `FULL_DDIV` | No | No | 0 F2P, 0 P2P | 0 / 84 | `PATCH_APPLICATION_FAILED` (git apply failed) |
