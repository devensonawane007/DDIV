# DDIV Full Benchmark Preflight Report: 40-Task QuixBugs Evaluation

**Preflight Timestamp:** 2026-10-16T06:48:15Z  
**Preflight Verdict:** **`READY`**  
**Model:** `qwen2.5-coder:7b` via local Ollama (`http://localhost:11434`)  
**Total Tasks:** 40 / 40 empirically verified tasks  
**Total Planned Runs:** 40 tasks × 3 conditions = **120 runs**  
**Cost:** $0.00 (100% local inference, zero cloud APIs)  

---

## Executive Summary

Following the successful resolution of persistent failure modes in the Phase 8.5 diagnostic experiment (`quicksort` resolved under `FULL_DDIV` Attempt 2; `rpn_eval` resolved across all conditions), the protocol enhancements have been **strictly frozen**.

This preflight report certifies that all 40 QuixBugs Python repair tasks have undergone empirical baseline screening, workspace isolation auditing, patch security gate testing, and local model verification. The system is verified **READY** for the full 40-task benchmark comparison.

---

## 1. Experimental Protocol & Frozen Architecture

The 40-task benchmark will evaluate automated program repair across three controlled experimental conditions under the frozen Phase 8.5 protocol:

1. **`BASELINE` (40 runs):** Exactly 1 attempt per task. Direct Coder repair attempt with deterministic greedy decoding (`T=0.0`). No supervisor, tester, memory, or retry mechanisms.
2. **`RETRY_ONLY` (40 runs):** Up to 3 attempts per task. Model receives raw sanitized pytest failure output (`[ORACLE_REDACTED]`) and prior-patch diff injection. Dynamic temperature schedule (`T=0.0` on Attempt 1, `T=0.2` on Attempt 2+). Supervisor, memory, and trust disabled.
3. **`FULL_DDIV` (40 runs):** Up to 3 attempts per task. Full multi-agent supervision with causal failure classification, prior-patch diff critique, mistake avoidance directives, anti-repetition detection, dynamic temperature schedule (`T=0.0` -> `T=0.2`), and isolated episodic memory logging (`quixbugs_40tasks_memory.db`).

---

## 2. Preflight Audit Checklist Across 40 Tasks

| Audit Gate | Verification Requirement | Status | Evidence / Notes |
| :--- | :--- | :---: | :--- |
| **Task Discovery** | 40 valid Python programs discovered | **PASS** | Exactly 40/40 tasks discovered in `QuixBugsAdapter` |
| **Defect Reproduction** | Empirical baseline reproduction on unpatched code | **PASS** | **40 / 40 tasks confirmed ELIGIBLE** with failing tests |
| **Timeout Handling** | Non-terminating loop detection fails closed | **PASS** | 4 infinite-loop tasks (`bitcount`, `find_first_in_sorted`, `mergesort`, `sqrt`) verified |
| **Workspace Isolation** | Agent workspaces contain 0 test files or JSON oracles | **PASS** | Verified across all 40 tasks (only target file + `node.py` when required) |
| **Empty Patch Gate** | Empty patch rejected fail-closed | **PASS** | Rejected as `EMPTY_PATCH` |
| **Invalid Format Gate** | Non-diff string rejected fail-closed | **PASS** | Rejected as `PATCH_FORMAT_INVALID` |
| **Security Gate** | Unauthorized file access / probe rejected | **PASS** | Rejected as `SECURITY_VIOLATION` |
| **Local Inference Route** | Local Ollama endpoint active and model present | **PASS** | `http://localhost:11434`, model `qwen2.5-coder:7b` confirmed |
| **Anchor Deduplication** | Sliding window anchor deduplication active | **PASS** | Multi-line sliding window deduplication verified |
| **Phase 8.4 Freeze** | Historical benchmark directory preserved | **PASS** | `results/quixbugs_benchmark_8tasks_20261016T084000Z/` intact |
| **Phase 8.5 Freeze** | Diagnostic directory preserved | **PASS** | `results/quixbugs_diagnostic_phase8_5_20261016T121200Z/` intact |
| **Production DB Safety** | Production memory database untouched | **PASS** | `data/ddiv_memory.db` pristine (mtime: Mon Oct  5 18:07:07 2026) |

---

## 3. Empirical Baseline Screening Breakdown (40 Tasks)

| # | Task ID | Program Name | Target File | Baseline Status | Tests (Fail/Total) | Duration |
| :-: | :--- | :--- | :--- | :---: | :---: | :---: |
| 1 | `quixbugs-python-bitcount` | `bitcount` | `python_programs/bitcount.py` | **ELIGIBLE [TIMEOUT]** | 1 / 1 | 5.089s |
| 2 | `quixbugs-python-breadth_first_search` | `breadth_first_search` | `python_programs/breadth_first_search.py` | **ELIGIBLE** | 1 / 5 | 1.86s |
| 3 | `quixbugs-python-bucketsort` | `bucketsort` | `python_programs/bucketsort.py` | **ELIGIBLE** | 1 / 2 | 1.317s |
| 4 | `quixbugs-python-depth_first_search` | `depth_first_search` | `python_programs/depth_first_search.py` | **ELIGIBLE** | 1 / 5 | 1.248s |
| 5 | `quixbugs-python-detect_cycle` | `detect_cycle` | `python_programs/detect_cycle.py` | **ELIGIBLE** | 1 / 6 | 1.287s |
| 6 | `quixbugs-python-find_first_in_sorted` | `find_first_in_sorted` | `python_programs/find_first_in_sorted.py` | **ELIGIBLE [TIMEOUT]** | 1 / 1 | 5.08s |
| 7 | `quixbugs-python-find_in_sorted` | `find_in_sorted` | `python_programs/find_in_sorted.py` | **ELIGIBLE** | 1 / 2 | 1.831s |
| 8 | `quixbugs-python-flatten` | `flatten` | `python_programs/flatten.py` | **ELIGIBLE** | 1 / 2 | 1.324s |
| 9 | `quixbugs-python-gcd` | `gcd` | `python_programs/gcd.py` | **ELIGIBLE** | 1 / 2 | 1.32s |
| 10 | `quixbugs-python-get_factors` | `get_factors` | `python_programs/get_factors.py` | **ELIGIBLE** | 1 / 2 | 1.353s |
| 11 | `quixbugs-python-hanoi` | `hanoi` | `python_programs/hanoi.py` | **ELIGIBLE** | 1 / 2 | 1.824s |
| 12 | `quixbugs-python-is_valid_parenthesization` | `is_valid_parenthesization` | `python_programs/is_valid_parenthesization.py` | **ELIGIBLE** | 1 / 2 | 1.317s |
| 13 | `quixbugs-python-kheapsort` | `kheapsort` | `python_programs/kheapsort.py` | **ELIGIBLE** | 1 / 2 | 1.3s |
| 14 | `quixbugs-python-knapsack` | `knapsack` | `python_programs/knapsack.py` | **ELIGIBLE** | 1 / 2 | 1.336s |
| 15 | `quixbugs-python-kth` | `kth` | `python_programs/kth.py` | **ELIGIBLE** | 1 / 2 | 1.825s |
| 16 | `quixbugs-python-lcs_length` | `lcs_length` | `python_programs/lcs_length.py` | **ELIGIBLE** | 1 / 2 | 1.358s |
| 17 | `quixbugs-python-levenshtein` | `levenshtein` | `python_programs/levenshtein.py` | **ELIGIBLE** | 1 / 2 | 2.973s |
| 18 | `quixbugs-python-lis` | `lis` | `python_programs/lis.py` | **ELIGIBLE** | 1 / 2 | 1.667s |
| 19 | `quixbugs-python-longest_common_subsequence` | `longest_common_subsequence` | `python_programs/longest_common_subsequence.py` | **ELIGIBLE** | 1 / 2 | 1.653s |
| 20 | `quixbugs-python-max_sublist_sum` | `max_sublist_sum` | `python_programs/max_sublist_sum.py` | **ELIGIBLE** | 1 / 2 | 1.324s |
| 21 | `quixbugs-python-mergesort` | `mergesort` | `python_programs/mergesort.py` | **ELIGIBLE [TIMEOUT]** | 1 / 1 | 5.105s |
| 22 | `quixbugs-python-minimum_spanning_tree` | `minimum_spanning_tree` | `python_programs/minimum_spanning_tree.py` | **ELIGIBLE** | 3 / 3 | 1.782s |
| 23 | `quixbugs-python-next_palindrome` | `next_palindrome` | `python_programs/next_palindrome.py` | **ELIGIBLE** | 1 / 2 | 1.235s |
| 24 | `quixbugs-python-next_permutation` | `next_permutation` | `python_programs/next_permutation.py` | **ELIGIBLE** | 1 / 1 | 1.363s |
| 25 | `quixbugs-python-pascal` | `pascal` | `python_programs/pascal.py` | **ELIGIBLE** | 1 / 2 | 1.307s |
| 26 | `quixbugs-python-possible_change` | `possible_change` | `python_programs/possible_change.py` | **ELIGIBLE** | 1 / 2 | 2.095s |
| 27 | `quixbugs-python-powerset` | `powerset` | `python_programs/powerset.py` | **ELIGIBLE** | 1 / 2 | 1.303s |
| 28 | `quixbugs-python-quicksort` | `quicksort` | `python_programs/quicksort.py` | **ELIGIBLE** | 1 / 2 | 1.234s |
| 29 | `quixbugs-python-reverse_linked_list` | `reverse_linked_list` | `python_programs/reverse_linked_list.py` | **ELIGIBLE** | 2 / 3 | 1.32s |
| 30 | `quixbugs-python-rpn_eval` | `rpn_eval` | `python_programs/rpn_eval.py` | **ELIGIBLE** | 1 / 2 | 1.717s |
| 31 | `quixbugs-python-shortest_path_length` | `shortest_path_length` | `python_programs/shortest_path_length.py` | **ELIGIBLE** | 2 / 4 | 1.33s |
| 32 | `quixbugs-python-shortest_path_lengths` | `shortest_path_lengths` | `python_programs/shortest_path_lengths.py` | **ELIGIBLE** | 4 / 4 | 1.267s |
| 33 | `quixbugs-python-shortest_paths` | `shortest_paths` | `python_programs/shortest_paths.py` | **ELIGIBLE** | 3 / 3 | 1.341s |
| 34 | `quixbugs-python-shunting_yard` | `shunting_yard` | `python_programs/shunting_yard.py` | **ELIGIBLE** | 1 / 2 | 1.777s |
| 35 | `quixbugs-python-sieve` | `sieve` | `python_programs/sieve.py` | **ELIGIBLE** | 1 / 2 | 1.319s |
| 36 | `quixbugs-python-sqrt` | `sqrt` | `python_programs/sqrt.py` | **ELIGIBLE [TIMEOUT]** | 1 / 1 | 5.098s |
| 37 | `quixbugs-python-subsequences` | `subsequences` | `python_programs/subsequences.py` | **ELIGIBLE** | 1 / 2 | 1.853s |
| 38 | `quixbugs-python-to_base` | `to_base` | `python_programs/to_base.py` | **ELIGIBLE** | 1 / 2 | 1.468s |
| 39 | `quixbugs-python-topological_ordering` | `topological_ordering` | `python_programs/topological_ordering.py` | **ELIGIBLE** | 3 / 3 | 1.386s |
| 40 | `quixbugs-python-wrap` | `wrap` | `python_programs/wrap.py` | **ELIGIBLE** | 1 / 1 | 1.308s |

---

## 4. Execution Budget & Resource Commitment

- **Total Tasks:** 40
- **Total Task-Condition Runs:** 120
- **Estimated Total Inference Requests:** ~120 to 280 local non-streaming calls
- **Estimated Wall-Clock Time:** ~30 to 45 minutes on local hardware
- **Financial Cost:** **$0.00** (Zero cloud API calls, 100% local Ollama inference)
- **Storage Footprint:** ~15 MB for workspace diffs, raw JSON artifacts, and isolated memory database

---

## 5. Preflight Readiness Verdict

**Verdict:** **`READY`**  
All 40 tasks empirically qualify, all security and isolation gates pass, and the Phase 8.5 protocol is frozen. Awaiting explicit user approval before launching the 40-task benchmark evaluation.