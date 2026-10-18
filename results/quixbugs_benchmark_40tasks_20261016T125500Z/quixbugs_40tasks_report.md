# DDIV Phase 8.6: Full 40-Task QuixBugs Automated Repair Report

**Execution Timestamp:** 2026-10-16T08:15:25Z  
**Model:** `qwen2.5-coder:7b` via local Ollama (`http://localhost:11434`)  
**Completed Tasks:** 40 / 40  
**Total Runs Completed:** 120 / 120  
**Elapsed Time:** 3132.59s  
**Cost:** $0.00 (100% local inference, zero cloud APIs)  

---

## Aggregate Summary Across Experimental Conditions

| Condition | Resolved | Resolution Rate | Total Tokens | Wall-Clock Duration |
| :--- | :---: | :---: | :---: | :---: |
| **`BASELINE`** (1 att, T=0.0) | 8 / 40 | 20.0% | 71,558 | 482.99s |
| **`RETRY_ONLY`** (up to 3 att, T=0.0/0.2, prior-patch diff) | 13 / 40 | 32.5% | 228,325 | 1291.69s |
| **`FULL_DDIV`** (up to 3 att, T=0.0/0.2, supervisor, memory, trust) | 13 / 40 | 32.5% | 225,458 | 1289.00s |

---

## Per-Task Repair Outcomes

| # | Task ID | Program Name | BASELINE (1 att) | RETRY_ONLY (<=3 att) | FULL_DDIV (<=3 att) |
| :-: | :--- | :--- | :---: | :---: | :---: |
|  1 | `quixbugs-python-bitcount` | `bitcount` | FAIL (1) | FAIL (3) | FAIL (3) |
|  2 | `quixbugs-python-breadth_first_search` | `breadth_first_search` | FAIL (1) | **RESOLVED** (2) | **RESOLVED** (2) |
|  3 | `quixbugs-python-bucketsort` | `bucketsort` | **RESOLVED** (1) | **RESOLVED** (1) | **RESOLVED** (1) |
|  4 | `quixbugs-python-depth_first_search` | `depth_first_search` | FAIL (1) | FAIL (3) | FAIL (3) |
|  5 | `quixbugs-python-detect_cycle` | `detect_cycle` | FAIL (1) | FAIL (3) | FAIL (3) |
|  6 | `quixbugs-python-find_first_in_sorted` | `find_first_in_sorted` | **RESOLVED** (1) | **RESOLVED** (1) | **RESOLVED** (1) |
|  7 | `quixbugs-python-find_in_sorted` | `find_in_sorted` | FAIL (1) | FAIL (3) | FAIL (3) |
|  8 | `quixbugs-python-flatten` | `flatten` | **RESOLVED** (1) | **RESOLVED** (1) | **RESOLVED** (1) |
|  9 | `quixbugs-python-gcd` | `gcd` | FAIL (1) | FAIL (3) | FAIL (3) |
| 10 | `quixbugs-python-get_factors` | `get_factors` | FAIL (1) | FAIL (3) | FAIL (3) |
| 11 | `quixbugs-python-hanoi` | `hanoi` | FAIL (1) | FAIL (3) | FAIL (3) |
| 12 | `quixbugs-python-is_valid_parenthesization` | `is_valid_parenthesization` | **RESOLVED** (1) | **RESOLVED** (1) | **RESOLVED** (1) |
| 13 | `quixbugs-python-kheapsort` | `kheapsort` | FAIL (1) | FAIL (3) | FAIL (3) |
| 14 | `quixbugs-python-knapsack` | `knapsack` | FAIL (1) | FAIL (3) | FAIL (3) |
| 15 | `quixbugs-python-kth` | `kth` | FAIL (1) | FAIL (3) | **RESOLVED** (2) |
| 16 | `quixbugs-python-lcs_length` | `lcs_length` | FAIL (1) | FAIL (3) | FAIL (3) |
| 17 | `quixbugs-python-levenshtein` | `levenshtein` | FAIL (1) | **RESOLVED** (2) | **RESOLVED** (2) |
| 18 | `quixbugs-python-lis` | `lis` | FAIL (1) | FAIL (3) | FAIL (3) |
| 19 | `quixbugs-python-longest_common_subsequence` | `longest_common_subsequence` | FAIL (1) | FAIL (3) | FAIL (3) |
| 20 | `quixbugs-python-max_sublist_sum` | `max_sublist_sum` | **RESOLVED** (1) | **RESOLVED** (1) | **RESOLVED** (1) |
| 21 | `quixbugs-python-mergesort` | `mergesort` | FAIL (1) | FAIL (3) | FAIL (3) |
| 22 | `quixbugs-python-minimum_spanning_tree` | `minimum_spanning_tree` | FAIL (1) | FAIL (3) | FAIL (3) |
| 23 | `quixbugs-python-next_palindrome` | `next_palindrome` | FAIL (1) | **RESOLVED** (3) | FAIL (3) |
| 24 | `quixbugs-python-next_permutation` | `next_permutation` | FAIL (1) | FAIL (3) | FAIL (3) |
| 25 | `quixbugs-python-pascal` | `pascal` | **RESOLVED** (1) | **RESOLVED** (1) | **RESOLVED** (1) |
| 26 | `quixbugs-python-possible_change` | `possible_change` | FAIL (1) | **RESOLVED** (2) | FAIL (3) |
| 27 | `quixbugs-python-powerset` | `powerset` | FAIL (1) | FAIL (3) | FAIL (3) |
| 28 | `quixbugs-python-quicksort` | `quicksort` | FAIL (1) | FAIL (3) | **RESOLVED** (2) |
| 29 | `quixbugs-python-reverse_linked_list` | `reverse_linked_list` | FAIL (1) | FAIL (3) | **RESOLVED** (3) |
| 30 | `quixbugs-python-rpn_eval` | `rpn_eval` | **RESOLVED** (1) | **RESOLVED** (1) | **RESOLVED** (1) |
| 31 | `quixbugs-python-shortest_path_length` | `shortest_path_length` | FAIL (1) | FAIL (3) | FAIL (3) |
| 32 | `quixbugs-python-shortest_path_lengths` | `shortest_path_lengths` | FAIL (1) | FAIL (3) | FAIL (3) |
| 33 | `quixbugs-python-shortest_paths` | `shortest_paths` | FAIL (1) | FAIL (3) | FAIL (3) |
| 34 | `quixbugs-python-shunting_yard` | `shunting_yard` | FAIL (1) | FAIL (3) | FAIL (3) |
| 35 | `quixbugs-python-sieve` | `sieve` | FAIL (1) | **RESOLVED** (3) | FAIL (3) |
| 36 | `quixbugs-python-sqrt` | `sqrt` | FAIL (1) | FAIL (3) | FAIL (3) |
| 37 | `quixbugs-python-subsequences` | `subsequences` | FAIL (1) | FAIL (3) | FAIL (3) |
| 38 | `quixbugs-python-to_base` | `to_base` | **RESOLVED** (1) | **RESOLVED** (1) | **RESOLVED** (1) |
| 39 | `quixbugs-python-topological_ordering` | `topological_ordering` | FAIL (1) | FAIL (3) | FAIL (3) |
| 40 | `quixbugs-python-wrap` | `wrap` | FAIL (1) | FAIL (3) | FAIL (3) |
