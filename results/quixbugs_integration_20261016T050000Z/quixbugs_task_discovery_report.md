# DDIV QuixBugs Python Benchmark: Task Discovery and Integration Report

**Generated:** 2026-10-16T05:00:00Z  
**Benchmark Source:** [QuixBugs Upstream Repository](https://github.com/jkoppel/QuixBugs)  
**Git Commit:** `4257f44b0ff1181dedaedee6a447e133219fcebf`  
**Local Path:** `data/quixbugs/`  
**Discovered Python Programs:** 40  
**Target Model Scope:** Smaller coding LLMs (e.g., `qwen2.5-coder:7b`)  

---

## 1. Executive Summary

- **Dataset Integration:** Official QuixBugs repository cloned cleanly to `data/quixbugs/` without disturbing historical SWE-bench datasets or configs.
- **Discovered Tasks:** Exactly **40 Python algorithmic repair tasks** were discovered, verified, and mapped 1-to-1 with their test modules.
- **Category Distribution:**
  - **Standard Data-Driven Tasks:** 31 tasks (evaluate against parameterized JSON testsuites in `json_testcases/`).
  - **Graph/Data-Structure Tasks:** 9 tasks (evaluate against programmatic test graphs using `node.py`).
- **Reference Solution Protection:** Upstream `correct_python_programs/` is strictly isolated and forbidden from entering agent workspaces.
- **Baseline Status:** All 40 tasks are initially cataloged as **`NOT_RUN`** and **`UNKNOWN`** eligibility pending controlled baseline verification.
- **Safety Guarantee:** Zero repair attempts, zero LLM calls, and zero external network calls were executed during this integration.

---

## 2. Dry-Run Inspection Command

To inspect discovered tasks from the command line without running any repairs or tests:

```powershell
python scripts/quixbugs_adapter.py --list-tasks
```

To inspect a single task's full specification:

```powershell
python scripts/quixbugs_adapter.py --task-id quixbugs-python-quicksort
```

---

## 3. Discovered Python Tasks Inventory (All 40 Programs)

| # | Task ID | Program Name | Source Path | Test Module Path | Category | Support Files | Baseline Status | Eligibility Status | Special Notes / Timeout Concerns |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `quixbugs-python-bitcount` | `bitcount` | `python_programs/bitcount.py` | `python_testcases/test_bitcount.py` | Standard | 3 files | **NOT_RUN** | **UNKNOWN** | CRITICAL TIMEOUT CONCERN: Bug causes an infinite loop ('n ^= n - 1') on positive numbers; test runner MUST enforce strict per-test timeout. |
| 2 | `quixbugs-python-breadth_first_search` | `breadth_first_search` | `python_programs/breadth_first_search.py` | `python_testcases/test_breadth_first_search.py` | Graph | 3 files | **NOT_RUN** | **UNKNOWN** | Graph-based (requires Node). Fails with IndexError on unreachable goals due to empty deque pop. |
| 3 | `quixbugs-python-bucketsort` | `bucketsort` | `python_programs/bucketsort.py` | `python_testcases/test_bucketsort.py` | Standard | 3 files | **NOT_RUN** | **UNKNOWN** | Standard unit test assertion defect. |
| 4 | `quixbugs-python-depth_first_search` | `depth_first_search` | `python_programs/depth_first_search.py` | `python_testcases/test_depth_first_search.py` | Graph | 3 files | **NOT_RUN** | **UNKNOWN** | Graph-based (requires Node). Recursion error or missing visited set on cyclic graphs. |
| 5 | `quixbugs-python-detect_cycle` | `detect_cycle` | `python_programs/detect_cycle.py` | `python_testcases/test_detect_cycle.py` | Graph | 3 files | **NOT_RUN** | **UNKNOWN** | Graph-based (requires Node). Tortoise-and-hare pointer advancement bug. |
| 6 | `quixbugs-python-find_first_in_sorted` | `find_first_in_sorted` | `python_programs/find_first_in_sorted.py` | `python_testcases/test_find_first_in_sorted.py` | Standard | 3 files | **NOT_RUN** | **UNKNOWN** | Binary search lower bound indexing error. |
| 7 | `quixbugs-python-find_in_sorted` | `find_in_sorted` | `python_programs/find_in_sorted.py` | `python_testcases/test_find_in_sorted.py` | Standard | 3 files | **NOT_RUN** | **UNKNOWN** | Binary search midpoint computation truncation error. |
| 8 | `quixbugs-python-flatten` | `flatten` | `python_programs/flatten.py` | `python_testcases/test_flatten.py` | Standard | 3 files | **NOT_RUN** | **UNKNOWN** | Standard unit test assertion defect. |
| 9 | `quixbugs-python-gcd` | `gcd` | `python_programs/gcd.py` | `python_testcases/test_gcd.py` | Standard | 3 files | **NOT_RUN** | **UNKNOWN** | Standard unit test assertion defect. |
| 10 | `quixbugs-python-get_factors` | `get_factors` | `python_programs/get_factors.py` | `python_testcases/test_get_factors.py` | Standard | 3 files | **NOT_RUN** | **UNKNOWN** | Standard unit test assertion defect. |
| 11 | `quixbugs-python-hanoi` | `hanoi` | `python_programs/hanoi.py` | `python_testcases/test_hanoi.py` | Standard | 3 files | **NOT_RUN** | **UNKNOWN** | Standard unit test assertion defect. |
| 12 | `quixbugs-python-is_valid_parenthesization` | `is_valid_parenthesization` | `python_programs/is_valid_parenthesization.py` | `python_testcases/test_is_valid_parenthesization.py` | Standard | 3 files | **NOT_RUN** | **UNKNOWN** | Standard unit test assertion defect. |
| 13 | `quixbugs-python-kheapsort` | `kheapsort` | `python_programs/kheapsort.py` | `python_testcases/test_kheapsort.py` | Standard | 3 files | **NOT_RUN** | **UNKNOWN** | Standard unit test assertion defect. |
| 14 | `quixbugs-python-knapsack` | `knapsack` | `python_programs/knapsack.py` | `python_testcases/test_knapsack.py` | Standard | 3 files | **NOT_RUN** | **UNKNOWN** | Standard unit test assertion defect. |
| 15 | `quixbugs-python-kth` | `kth` | `python_programs/kth.py` | `python_testcases/test_kth.py` | Standard | 3 files | **NOT_RUN** | **UNKNOWN** | Quickselect partition index offset. |
| 16 | `quixbugs-python-lcs_length` | `lcs_length` | `python_programs/lcs_length.py` | `python_testcases/test_lcs_length.py` | Standard | 3 files | **NOT_RUN** | **UNKNOWN** | Standard unit test assertion defect. |
| 17 | `quixbugs-python-levenshtein` | `levenshtein` | `python_programs/levenshtein.py` | `python_testcases/test_levenshtein.py` | Standard | 3 files | **NOT_RUN** | **UNKNOWN** | Recursive string distance without memoization; slow on long test strings. |
| 18 | `quixbugs-python-lis` | `lis` | `python_programs/lis.py` | `python_testcases/test_lis.py` | Standard | 3 files | **NOT_RUN** | **UNKNOWN** | Standard unit test assertion defect. |
| 19 | `quixbugs-python-longest_common_subsequence` | `longest_common_subsequence` | `python_programs/longest_common_subsequence.py` | `python_testcases/test_longest_common_subsequence.py` | Standard | 3 files | **NOT_RUN** | **UNKNOWN** | Recursive string subsequence matching without memoization; potential latency. |
| 20 | `quixbugs-python-max_sublist_sum` | `max_sublist_sum` | `python_programs/max_sublist_sum.py` | `python_testcases/test_max_sublist_sum.py` | Standard | 3 files | **NOT_RUN** | **UNKNOWN** | Kadane's algorithm initialization on all-negative sequences. |
| 21 | `quixbugs-python-mergesort` | `mergesort` | `python_programs/mergesort.py` | `python_testcases/test_mergesort.py` | Standard | 3 files | **NOT_RUN** | **UNKNOWN** | Merge loop comparison operator handling. |
| 22 | `quixbugs-python-minimum_spanning_tree` | `minimum_spanning_tree` | `python_programs/minimum_spanning_tree.py` | `python_testcases/test_minimum_spanning_tree.py` | Graph | 3 files | **NOT_RUN** | **UNKNOWN** | Graph-based (requires Node). Disjoint-set forest union-find weight handling. |
| 23 | `quixbugs-python-next_palindrome` | `next_palindrome` | `python_programs/next_palindrome.py` | `python_testcases/test_next_palindrome.py` | Standard | 3 files | **NOT_RUN** | **UNKNOWN** | Potential infinite loop on edge cases if digit wrap logic fails. |
| 24 | `quixbugs-python-next_permutation` | `next_permutation` | `python_programs/next_permutation.py` | `python_testcases/test_next_permutation.py` | Standard | 3 files | **NOT_RUN** | **UNKNOWN** | Standard unit test assertion defect. |
| 25 | `quixbugs-python-pascal` | `pascal` | `python_programs/pascal.py` | `python_testcases/test_pascal.py` | Standard | 3 files | **NOT_RUN** | **UNKNOWN** | Standard unit test assertion defect. |
| 26 | `quixbugs-python-possible_change` | `possible_change` | `python_programs/possible_change.py` | `python_testcases/test_possible_change.py` | Standard | 3 files | **NOT_RUN** | **UNKNOWN** | Standard unit test assertion defect. |
| 27 | `quixbugs-python-powerset` | `powerset` | `python_programs/powerset.py` | `python_testcases/test_powerset.py` | Standard | 3 files | **NOT_RUN** | **UNKNOWN** | Standard unit test assertion defect. |
| 28 | `quixbugs-python-quicksort` | `quicksort` | `python_programs/quicksort.py` | `python_testcases/test_quicksort.py` | Standard | 3 files | **NOT_RUN** | **UNKNOWN** | Strict inequality drops duplicate pivot elements ('x < pivot' and 'x > pivot'). |
| 29 | `quixbugs-python-reverse_linked_list` | `reverse_linked_list` | `python_programs/reverse_linked_list.py` | `python_testcases/test_reverse_linked_list.py` | Graph | 3 files | **NOT_RUN** | **UNKNOWN** | Graph-based (requires Node). Pointer reversal boundary condition. |
| 30 | `quixbugs-python-rpn_eval` | `rpn_eval` | `python_programs/rpn_eval.py` | `python_testcases/test_rpn_eval.py` | Standard | 3 files | **NOT_RUN** | **UNKNOWN** | Reverse Polish stack operand order inverted for binary subtraction/division. |
| 31 | `quixbugs-python-shortest_path_length` | `shortest_path_length` | `python_programs/shortest_path_length.py` | `python_testcases/test_shortest_path_length.py` | Graph | 3 files | **NOT_RUN** | **UNKNOWN** | Graph-based (requires Node). Dijkstra priority distance relaxation. |
| 32 | `quixbugs-python-shortest_path_lengths` | `shortest_path_lengths` | `python_programs/shortest_path_lengths.py` | `python_testcases/test_shortest_path_lengths.py` | Graph | 3 files | **NOT_RUN** | **UNKNOWN** | Graph-based (requires Node). Matrix distance initialization in Floyd-Warshall. |
| 33 | `quixbugs-python-shortest_paths` | `shortest_paths` | `python_programs/shortest_paths.py` | `python_testcases/test_shortest_paths.py` | Graph | 3 files | **NOT_RUN** | **UNKNOWN** | Graph-based (requires Node). Bellman-Ford edge relaxation iteration limit. |
| 34 | `quixbugs-python-shunting_yard` | `shunting_yard` | `python_programs/shunting_yard.py` | `python_testcases/test_shunting_yard.py` | Standard | 3 files | **NOT_RUN** | **UNKNOWN** | Standard unit test assertion defect. |
| 35 | `quixbugs-python-sieve` | `sieve` | `python_programs/sieve.py` | `python_testcases/test_sieve.py` | Standard | 3 files | **NOT_RUN** | **UNKNOWN** | Standard unit test assertion defect. |
| 36 | `quixbugs-python-sqrt` | `sqrt` | `python_programs/sqrt.py` | `python_testcases/test_sqrt.py` | Standard | 3 files | **NOT_RUN** | **UNKNOWN** | Newton-Raphson approximation epsilon stopping condition. |
| 37 | `quixbugs-python-subsequences` | `subsequences` | `python_programs/subsequences.py` | `python_testcases/test_subsequences.py` | Standard | 3 files | **NOT_RUN** | **UNKNOWN** | Standard unit test assertion defect. |
| 38 | `quixbugs-python-to_base` | `to_base` | `python_programs/to_base.py` | `python_testcases/test_to_base.py` | Standard | 3 files | **NOT_RUN** | **UNKNOWN** | Standard unit test assertion defect. |
| 39 | `quixbugs-python-topological_ordering` | `topological_ordering` | `python_programs/topological_ordering.py` | `python_testcases/test_topological_ordering.py` | Graph | 3 files | **NOT_RUN** | **UNKNOWN** | Graph-based (requires Node). In-degree tracking and queue processing. |
| 40 | `quixbugs-python-wrap` | `wrap` | `python_programs/wrap.py` | `python_testcases/test_wrap.py` | Standard | 3 files | **NOT_RUN** | **UNKNOWN** | Text wrapping column break and paragraph split logic. |

---

## 4. Architecture and Adapter Design

### 4.1 Minimal Non-Invasive Integration Point

- **Module Location:** `evaluation/quixbugs_adapter.py` with CLI wrapper in `scripts/quixbugs_adapter.py`.
- **Normalized Schema:** `QuixBugsTask` standardizes task ID, source target, test command, support files, and neutral issue descriptions.
- **Evaluator Abstraction:** `QuixBugsEvaluator` evaluates patches independently from SWE-bench Docker harnesses, providing native pytest parsing, individual test outcome tracking, and timeout defense.

### 4.2 Reference Solution Protection Architecture

```text
data/quixbugs/ (Upstream Dataset)
├── correct_python_programs/  <-- [FORBIDDEN: NEVER ACCESSED BY AGENT OR COPIED TO WORKSPACE]
├── python_programs/          <-- Source of buggy files
├── python_testcases/         <-- Source of test suites
└── json_testcases/           <-- Source of test fixtures

          │ (QuixBugsAdapter.create_task_workspace)
          ▼
data/workspaces/<task_id>-agent/ (Isolated Task Workspace)
├── python_programs/<algo>.py <-- Single target file agent can edit
├── python_testcases/test_<algo>.py
├── conftest.py
└── [correct_python_programs/ DOES NOT EXIST - LEAK GATE ENFORCED]
```

---

## 5. Offline Integration Verification Results

The adapter test suite was executed offline (`python -m pytest -v tests/test_quixbugs_adapter.py`):

| Test Case | Scope Verified | Outcome |
|---|---|---|
| `test_task_discovery_synthetic` | Synthetic benchmark discovery and schema validation | **PASSED** |
| `test_task_discovery_real_dataset` | Discovery of all 40 real Python tasks in `data/quixbugs` | **PASSED** |
| `test_workspace_creation_isolation_and_reference_exclusion` | Verifies workspace contains target and test, strictly omits reference | **PASSED** |
| `test_reference_leak_prevention_gate` | Asserts fail-closed `RuntimeError` if reference solutions ever leak | **PASSED** |
| `test_patch_application_and_evaluation_resolved` | Applies valid diff, executes test, confirms `RESOLVED` | **PASSED** |
| `test_reject_empty_and_invalid_patches` | Rejects empty, whitespace, and malformed diffs | **PASSED** |
| `test_individual_test_outcome_preservation` | Distinguishes passing vs failing cases in same module | **PASSED** |
| `test_timeout_handling_infinite_loop` | Catches infinite loops via timeout, marks `TIMEOUT` failure | **PASSED** |
| `test_baseline_eligibility_checker` | Confirms pre-repair defect reproduction mechanism | **PASSED** |
| `test_task_listing_zero_llm_calls` | Proves task listing is instant and strictly offline | **PASSED** |

**Test Result:** `10 passed in 11.97s` (100% pass rate).

---

## 6. Next Steps (Future Phase)

1. **Baseline Screening Run:** Execute unpatched tests for all 40 tasks with timeout protection to empirically classify `ELIGIBLE` vs `NEEDS_RECHECK`.
2. **Repair Experiment Gating:** Once tasks are confirmed baseline-eligible, launch controlled DDIV repair trials with `qwen2.5-coder:7b` without altering SWE-bench benchmarks.
