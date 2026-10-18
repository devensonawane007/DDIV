# QuixBugs Phase 8.2: Baseline Screening Preflight Report

**Benchmark:** QuixBugs Python Repair Benchmark  
**Checkout Path:** `D:/DDIV/data/quixbugs`  
**Git Commit:** `4257f44b0ff1181dedaedee6a447e133219fcebf`  
**Preflight Timestamp:** 2026-10-16T05:45:00Z  
**Phase Status:** **PREFLIGHT COMPLETE — PENDING USER APPROVAL TO EXECUTE**

---

## 1. Subprocess Execution & Process Isolation Audit

### 1.1 Process Execution Architecture
A read-only code audit was conducted on `evaluation/quixbugs_adapter.py` and `evaluation/context_builder.py`.

- **Subprocess Execution Confirmed:**
  Both patch evaluation (`evaluate_patch`, lines 594-603) and baseline defect verification (`check_baseline_eligibility`, lines 758-767) execute tests exclusively via an **external Python subprocess** using `subprocess.run([sys.executable, "-c", runner_code], ...)`.
  Neither routine invokes `pytest.main()` inside the parent DDIV process.
- **Parent Process Purity:**
  The parent process's `sys.path`, `sys.modules` module cache, working directory, and environment variables remain 100% untouched throughout execution.
- **Subprocess Cleanliness:**
  Each subprocess is executed with `cwd` pointing to an isolated `tempfile.TemporaryDirectory`. When the subprocess completes, the operating system reclaims all process memory, file handles, and loaded module state. The temporary directory is immediately purged upon context manager exit.

### 1.2 Documentation Correction
Any prior documentation or comments mentioning `pytest.main` without clarifying process boundary have been corrected in `evaluation/quixbugs_adapter.py`. The docstrings now explicitly state:
> *"Pytest executes in an isolated external Python subprocess from a temporary working directory with candidate workspace prepended to sys.path, ensuring candidate code is tested without copying tests into the agent workspace and completely preventing persistent sys.path or sys.modules module-cache contamination in the parent process."*

---

## 2. Test Execution against Candidate Workspace vs Hidden Oracles

### 2.1 Candidate Workspace Import Precedence
In standard pytest execution with `cwd=quixbugs_root`, pytest prepends the test file's directory to `sys.path[0]`, causing Python to import unpatched code from `quixbugs_root/python_programs` instead of candidate workspace patches.
In DDIV's hardened evaluator runner:
1. `sys.path.insert(0, repr(ws_str))` forces Python to search the candidate workspace first.
2. `sys.path.insert(1, repr(py_test_dir))` enables test fixtures to load support files (`load_testdata.py`, `node.py`).
3. `sys.path.insert(2, repr(qb_root_str))` loads repository configurations.
4. `--import-mode=append` instructs pytest to append test directories to `sys.path` rather than prepending them to index 0.

This import resolution mechanism was empirically validated in `tests/test_quixbugs_isolation.py::TestQuixBugsIsolation::test_06_evaluator_imports_candidate_code_not_repository_or_gold`.

### 2.2 Oracle Inaccessibility to Model-Facing Agents
- **Workspace Isolation:** `create_agent_workspace` provisions exclusively `python_programs/<prog>.py` (and `node.py` for graph algorithms). Test scripts (`python_testcases/`) and JSON test data (`json_testcases/`) are never copied.
- **Path Traversal & Symlink Defense:** `TargetedContextBuilder.build_context` enforces canonical workspace containment (`fpath.resolve().is_relative_to(ws.resolve())`), neutralizing `../../`, absolute paths, and external symlinks.
- **Output Sanitization:** All pytest outputs are piped through `sanitize_evaluator_output`. Test parametrization arguments (`[input-expected]`) are redacted to `[case_test]`, and assertion operands are replaced with `[ORACLE_REDACTED]`.
- **Zero Agent Tools:** Model-facing agents (`CoderAgent`, `LocatorAgent`, `TesterAgent`, `SupervisorAgent`) possess zero shell or file-read tools.

---

## 3. Timeout Enforcement, Workspace Cleanup, and Task-to-Task Isolation

### 3.1 Timeout Enforcement
- **Baseline Screening Timeout:** 10 seconds per task.
- **Candidate Patch Evaluation Timeout:** 15 seconds per patch attempt.
- Subprocess timeouts are strictly enforced by `subprocess.run(..., timeout=timeout)`. If an unpatched or candidate patch enters an infinite loop, `subprocess.TimeoutExpired` is caught, killing the subprocess, marking `is_timeout=True`, and categorizing the outcome as `TIMEOUT`.

### 3.2 Workspace Cleanup & Concurrency Isolation
- Each baseline check creates a fresh `tempfile.TemporaryDirectory` for the agent workspace and a separate `tempfile.TemporaryDirectory` for the evaluator execution directory.
- `create_agent_workspace(task_id, dest_dir)` explicitly purges `dest_dir` if it already exists before creating a new workspace.
- Consecutive tasks run in mutually disjoint directories with fresh subprocesses, eliminating any cross-task contamination.

---

## 4. Proposed Baseline Screening Batch (8 Tasks)

### 4.1 Selection Rationale
To ensure clean, reproducible baseline defect verification before introducing complex recovery or repair experiments, 8 tasks were selected according to the following criteria:
1. **Source Code Simplicity:** Very compact implementations (8 to 23 lines of code), enabling transparent AST inspection and fast reasoning.
2. **Deterministic Defect Manifestation:** The unpatched code fails deterministically with assertion or logic errors on test inputs without hanging.
3. **Exclusion of Known Timeout-Prone Tasks:** Tasks with known infinite loops or infinite recursions in their buggy implementations are initially excluded to eliminate false timeouts during initial screening:
   - `bitcount`: Buggy while loop `n ^= n - 1` with $n=127$ never terminates.
   - `sqrt`: Buggy condition `while abs(x - approx) > epsilon` checks difference against $x$ rather than $x - \text{approx}^2$, hanging indefinitely for $x \ge 2$.
   - `gcd`: Buggy recursive call `gcd(a % b, b)` never decreases $b$, causing maximum recursion depth exceptions.
4. **Exclusion of Graph-Based Tasks:** Excludes graph tasks (`breadth_first_search`, `detect_cycle`, etc.) from the first batch to avoid class dependency variables (`node.py`) and keep the initial test environment 100% uniform (pure JSONL parameterized fixtures).
5. **Zero Setup Cost:** Requires no compiler, no container, and no external dependencies beyond the local Python 3.11 environment.

### 4.2 Proposed 8-Task Batch Specification

| # | Task ID | Target Source File | Test Module | Timeout | Known Defect Summary | Expected Failure Mode |
| :-: | :--- | :--- | :--- | :-: | :--- | :--- |
| 1 | `quixbugs-python-bucketsort` | `python_programs/bucketsort.py` | `python_testcases/test_bucketsort.py` | 10s | Iterates `enumerate(arr)` instead of `enumerate(counts)`. | `ASSERTION_FAILURE` (IndexError / malformed array) |
| 2 | `quixbugs-python-flatten` | `python_programs/flatten.py` | `python_testcases/test_flatten.py` | 10s | Recursion base case yields `flatten(x)` generator instead of scalar `x`. | `ASSERTION_FAILURE` (Nested generator in output) |
| 3 | `quixbugs-python-is_valid_parenthesization` | `python_programs/is_valid_parenthesization.py` | `python_testcases/test_is_valid_parenthesization.py` | 10s | Returns `True` unconditionally at end of loop instead of `depth == 0`. | `ASSERTION_FAILURE` (Returns True on unbalanced open parens) |
| 4 | `quixbugs-python-max_sublist_sum` | `python_programs/max_sublist_sum.py` | `python_testcases/test_max_sublist_sum.py` | 10s | Kadane's algorithm omits reset to 0: `max_ending_here + x` without `max(0, ...)`. | `ASSERTION_FAILURE` (Negative prefix fails max sum) |
| 5 | `quixbugs-python-pascal` | `python_programs/pascal.py` | `python_testcases/test_pascal.py` | 10s | Inner column loop range `range(0, r)` truncates the rightmost 1 in each row. | `ASSERTION_FAILURE` (Truncated Pascal rows) |
| 6 | `quixbugs-python-quicksort` | `python_programs/quicksort.py` | `python_testcases/test_quicksort.py` | 10s | Strict partition comparisons `x > pivot` and `x < pivot` drop duplicate values. | `ASSERTION_FAILURE` (Duplicates omitted from sorted output) |
| 7 | `quixbugs-python-rpn_eval` | `python_programs/rpn_eval.py` | `python_testcases/test_rpn_eval.py` | 10s | Stack operand order inversion: passes `a, b` to `op` instead of `b, a`. | `ASSERTION_FAILURE` (Subtractions/divisions inverted) |
| 8 | `quixbugs-python-to_base` | `python_programs/to_base.py` | `python_testcases/test_to_base.py` | 10s | Digit concatenation order: `result + alphabet[i]` appends rather than prepending. | `ASSERTION_FAILURE` (Base representation digits reversed) |

---

## 5. Baseline Eligibility Classification Criteria

Each task in the baseline screening must be classified into one of three unambiguous categories:

1. **`ELIGIBLE` (Defect Reproduced):**
   - The test suite executes cleanly without environment, import, or syntax errors.
   - At least one specification test in `test_<prog>.py` fails on the unpatched code due to the intended defect.
   - Total tests executed $> 0$ and failed tests $> 0$.
2. **`INELIGIBLE` (Defect Not Present / Tests Already Pass):**
   - The unpatched code passes 100% of specification tests. No defect to repair.
3. **`NEEDS_RECHECK` (Environment or Execution Failure):**
   - The test suite fails due to an environmental or harness problem rather than the code defect (e.g. `ImportError`, `ModuleNotFoundError`, missing test fixture, syntax error during test discovery, or zero tests collected).

---

## 6. Protection of Gold Reference Solutions

- **No Reference Leakage:** `correct_python_programs/`, `correct_java_programs/`, and Java source/tests are strictly excluded from:
  - Agent workspaces.
  - Model prompts (Coder, Locator, Tester, Supervisor).
  - Sanitized execution diagnostics.
  - Episodic memory (`ddiv_memory.db`).
- **Prompt Contents for Repair Agents:**
  Model-facing agents will receive **only**:
  1. The task ID and program name.
  2. The buggy implementation source code loaded directly from the isolated agent workspace.
  3. The docstring specification embedded in the source file header.
  4. Sanitized failure feedback (`AssertionError: candidate output did not match expected output [ORACLE_REDACTED]`).

---

## 7. Resource & Runtime Estimates

| Metric | Estimate for 8-Task Baseline Screening | Notes |
| :--- | :---: | :--- |
| **Total Wall-Clock Runtime** | ~2.5 – 4.0 seconds | Subprocess spawn + pytest collection overhead (~0.25s per task). |
| **CPU Utilization** | < 5% single-core | Fast Python AST and in-memory test execution. |
| **GPU Utilization** | **0.0% (Zero)** | Baseline screening executes existing tests without model inference. |
| **Disk Requirements** | < 1 MB | Temporary workspaces and small JSON/markdown result files. |
| **External Network Calls** | **0 (Zero)** | Completely offline execution. |
| **Model/LLM Calls** | **0 (Zero)** | Completely offline execution. |

---

## 8. Preflight Sign-Off & Next Steps

This preflight audit confirms that all ground-truth isolation boundaries, subprocess execution barriers, diagnostic sanitizers, and task definitions are fully operational and verified offline.

**Current Action:** Stopped for user review and explicit approval before running the 8-task baseline screening batch.
