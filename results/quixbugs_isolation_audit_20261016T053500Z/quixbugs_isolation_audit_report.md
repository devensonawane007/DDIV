# QuixBugs Ground-Truth Isolation Audit and Verification Report

**Benchmark:** QuixBugs Python Repair Benchmark  
**Checkout Path:** `D:/DDIV/data/quixbugs`  
**Git Commit:** `4257f44b0ff1181dedaedee6a447e133219fcebf`  
**Date of Audit:** October 16, 2026  
**Auditor:** DDIV Automated Verification & Security Subsystem  
**Overall Isolation Status:** **VERIFIED**

---

## 1. Executive Summary

During Phase 8 integration of QuixBugs, initial workspace setup copied `python_testcases/` and `json_testcases/` directly into task workspaces. A preliminary audit revealed that `json_testcases/<program>.json` files contain explicit input-output pairs `[[input], expected]`, exposing the ground-truth test oracle directly to any file-reading or context-gathering routine. Furthermore, un-sanitized pytest failure outputs emitted exact expected literal values (`assert actual == expected`), which downstream recovery mechanisms would supply to LLM prompts.

In Phase 8.1, a rigorous ground-truth isolation architecture was designed, implemented, and verified offline across all 40 QuixBugs Python tasks.

### Key Audit Findings & Enforcement:
1. **Two-Workspace Architecture:** Agent workspaces receive **solely** the buggy implementation file (`python_programs/<prog>.py`) and, for 9 graph tasks, the immutable data structure definition (`python_programs/node.py`). Test suites and JSON oracles remain strictly in the external benchmark root.
2. **Fail-Closed Workspace Gate:** Workspace creation performs an exhaustive scan for test files, JSON fixtures, and reference folders (`correct*`). If any forbidden file is discovered, the workspace is immediately purged and a `RuntimeError` is raised.
3. **Subprocess Pytest Runner with Precise Import Precedence:** An isolated runner executes pytest out-of-process with candidate workspace injected at `sys.path[0]`, working directory bound to a clean temporary folder, and `--import-mode=append`. This ensures pytest imports and tests the candidate workspace patch without importing upstream or reference implementations.
4. **Diagnostic & Failure Output Sanitizer:** Pytest stdout/stderr and failure summaries are sanitized to strip parametrization arguments, variable dumps (`input_data = ...`, `expected = ...`), assertion comparison expressions, and patch diffs. The agent only receives `AssertionError: candidate output did not match expected output [ORACLE_REDACTED]`.
5. **Static Patch Security Gate:** Candidate patches are statically parsed (AST and token analysis). Patches attempting to edit non-target files, read external files (`open`), execute processes (`subprocess`, `os.system`), or inspect Python internals (`__import__`) are rejected prior to evaluation.
6. **Canonical Path Containment in Context Builder:** `TargetedContextBuilder` resolves all paths to their canonical representation (`fpath.resolve()`) and verifies `is_relative_to(workspace.resolve())`, neutralizing `../` relative traversal, absolute path leakage, and external symlinks.
7. **Model-Facing Agent Boundary:** Confirmed that `CoderAgent`, `LocatorAgent`, `TesterAgent`, and `SupervisorAgent` are pure Pydantic JSON transformation agents with zero tool definitions, zero shell access, and zero direct filesystem access.

---

## 2. Asset Classification Matrix

| Asset Path | Asset Role | Agent Visible? | Evaluator Visible? | Protection & Isolation Rule |
| :--- | :--- | :---: | :---: | :--- |
| `python_programs/<prog>.py` | Target buggy implementation | **YES** | YES | Copied to agent workspace. Target of repair patch. |
| `python_programs/node.py` | Graph node class definition | **YES** (graph only) | YES | Copied to workspace only for 9 graph-based algorithms. |
| `python_testcases/test_<prog>.py` | Pytest test suite | **NO** | YES | Kept exclusively in evaluator root. Never copied to agent workspace. |
| `python_testcases/conftest.py` | Pytest configuration | **NO** | YES | Kept exclusively in evaluator root. |
| `python_testcases/load_testdata.py` | Test loader utility | **NO** | YES | Kept exclusively in evaluator root. |
| `json_testcases/<prog>.json` | Expected I/O oracle values | **NO** | YES | Kept exclusively in evaluator root. Ground-truth inputs & expected outputs. |
| `correct_python_programs/` | Human reference solutions | **NO** | **NO** | Strictly excluded from all workspaces, evaluators, prompts, and memory. |
| `correct_java_programs/` | Java reference solutions | **NO** | **NO** | Strictly excluded. |
| `java_programs/` | Java benchmark source | **NO** | **NO** | Strictly excluded. |
| `java_testcases/` | Java benchmark testcases | **NO** | **NO** | Strictly excluded. |

---

## 3. Implementation Changes

### 3.1 `evaluation/quixbugs_adapter.py`
- **Replaced `create_task_workspace` with `create_agent_workspace`:**
  - Isolates candidate workspace by copying only `python_programs/<program>.py` (and `node.py` if graph task).
  - Implemented `_enforce_agent_workspace_isolation`: Recursively scans candidate workspace; immediately raises `RuntimeError("CRITICAL ISOLATION BREACH")` and removes directory if any test or oracle file is detected.
- **Implemented `validate_patch_security`:**
  - Rejects patches modifying any file other than the designated target file.
  - Inspects AST and forbidden tokens (`open(`, `subprocess`, `os.system`, `__import__`, `eval(`, `exec(`, `sys.modules`) to block exploit payloads.
- **Hardened `evaluate_patch` and `check_baseline_eligibility`:**
  - Runs isolated runner script in a dedicated temporary directory.
  - Injects candidate workspace at `sys.path[0]` and passes `--import-mode=append` to `pytest.main`.
  - Captures test results and pipes all stdout/stderr through `sanitize_evaluator_output`.
- **Implemented `sanitize_evaluator_output`:**
  - Strips test parametrization values: `test_algo[input-expected]` -> `test_algo[case_test]`.
  - Redacts assertion literals and variable dumps: `AssertionError: assert ... == ...` -> `AssertionError: candidate output did not match expected output [ORACLE_REDACTED]`.
  - Strips expected output dumps and diff lines.

### 3.2 `evaluation/context_builder.py`
- **Canonical Workspace Containment:**
  - Resolves target files using `fpath.resolve()` and checks `fpath.is_relative_to(workspace_path.resolve())`.
  - Rejects external symlinks and relative traversal (`../`).
  - Iterates dynamically across candidate files up to the file budget rather than slicing prior to security checks.

### 3.3 `data/quixbugs/quixbugs_manifest.json`
- Upgraded manifest to version 1.1, incorporating `ground_truth_isolation` metadata, explicit defense layer specifications, and verified audit status.

### 3.4 `scripts/quixbugs_adapter.py`
- Added `--audit-isolation` CLI flag allowing automated offline auditing of all 40 task workspaces.

---

## 4. Demonstrated Isolation Boundary Verification

### 4.1 Pytest Import Resolution Demonstration
Under default pytest behavior with `cwd=quixbugs_root`, pytest prepends the test file directory to `sys.path[0]`, resulting in Python importing the original unpatched code from `quixbugs_root/python_programs` instead of the candidate workspace.
In DDIV's hardened evaluator:
1. `cwd` is set to an empty temporary directory (`tempfile.TemporaryDirectory`).
2. Candidate workspace is inserted at `sys.path[0]`.
3. `--import-mode=append` prevents pytest from reordering `sys.path`.
This guarantees that candidate code is executed during evaluation while test fixtures load from the benchmark root. Verified in `test_06_evaluator_imports_candidate_code_not_repository_or_gold`.

### 4.2 Output Sanitization Demonstration
When an unpatched or incorrect patch is evaluated, raw pytest output contains:
```
> assert algo_secret('SYNTHETIC_INPUT_CANARY_ARG_123456789') == 'SYNTHETIC_ORACLE_CANARY_VALUE_987654321'
E AssertionError: assert 'wrong_output' == 'SYNTHETIC_ORACLE_CANARY_VALUE_987654321'
```
After `sanitize_evaluator_output`:
```
E AssertionError: candidate output did not match expected output [ORACLE_REDACTED]
```
Verified in `test_05_logs_and_recovery_diagnostics_sanitization_no_oracle_leak`.

---

## 5. Offline Leakage & Isolation Test Results

Full test suite executed offline with zero network and zero LLM calls:
Command: `pytest -v tests/test_quixbugs_adapter.py tests/test_quixbugs_isolation.py`
Runtime: **15.03 seconds** | **19 passed, 0 failed, 0 warnings**

### Test Breakdown:
| Test ID | Test Description | Result |
| :--- | :--- | :---: |
| `test_quixbugs_adapter.py::test_task_discovery_synthetic` | Task discovery on synthetic repository structure | **PASSED** |
| `test_quixbugs_adapter.py::test_task_discovery_real_dataset` | Discovery of all 40 tasks on real dataset | **PASSED** |
| `test_quixbugs_adapter.py::test_workspace_creation_isolation_and_reference_exclusion` | Verifies tests/JSON excluded from workspace | **PASSED** |
| `test_quixbugs_adapter.py::test_reference_leak_prevention_gate` | Reference directory exclusion validation | **PASSED** |
| `test_quixbugs_adapter.py::test_patch_application_and_evaluation_resolved` | Valid patch evaluation to RESOLVED | **PASSED** |
| `test_quixbugs_adapter.py::test_reject_empty_and_invalid_patches` | Rejection of empty/corrupt diffs | **PASSED** |
| `test_quixbugs_adapter.py::test_individual_test_outcome_preservation` | Granular per-test pass/fail status tracking | **PASSED** |
| `test_quixbugs_adapter.py::test_timeout_handling_infinite_loop` | Pytest timeout handling on infinite loops | **PASSED** |
| `test_quixbugs_adapter.py::test_baseline_eligibility_checker` | Initial buggy failure eligibility check | **PASSED** |
| `test_quixbugs_adapter.py::test_task_listing_zero_llm_calls` | Zero LLM calls invoked during discovery/listing | **PASSED** |
| `test_quixbugs_isolation.py::test_01_synthetic_oracle_secret_absence` | Canary secrets 100% absent from agent workspace | **PASSED** |
| `test_quixbugs_isolation.py::test_02_all_40_real_quixbugs_agent_workspaces` | All 40 real workspaces strictly isolated & clean | **PASSED** |
| `test_quixbugs_isolation.py::test_03_path_traversal_and_symlink_defense` | `../`, absolute paths & symlinks blocked | **PASSED** |
| `test_quixbugs_isolation.py::test_04_model_facing_agent_permissions_audit` | Confirms zero shell/file tools on model agents | **PASSED** |
| `test_quixbugs_isolation.py::test_05_logs_and_recovery_diagnostics_sanitization` | Pytest outputs redact expected oracle literals | **PASSED** |
| `test_quixbugs_isolation.py::test_06_evaluator_imports_candidate_code` | Evaluator imports candidate code, not gold | **PASSED** |
| `test_quixbugs_isolation.py::test_07_malicious_patch_security_gate` | File I/O & subprocess patches fail closed | **PASSED** |
| `test_quixbugs_isolation.py::test_08_fail_closed_gate_on_workspace_contamination` | Auto-purge & RuntimeError on contamination | **PASSED** |
| `test_quixbugs_isolation.py::test_09_memory_sanitization_strips_reference_tokens` | Episodic memory cleans reference & oracle tokens | **PASSED** |

---

## 6. Audit Conclusion & Isolation Status

**Final Status: VERIFIED**

The QuixBugs Python Benchmark integration now adheres strictly to DDIV's ground-truth isolation standard. The agent workspace contains zero test cases, zero expected outputs, and zero reference solutions. The evaluation process is strictly decoupled, outputs are sanitized against oracle leakage, and candidate patches are restricted by static security gates.

The adapter is safe for future baseline screening and repair experiments.
