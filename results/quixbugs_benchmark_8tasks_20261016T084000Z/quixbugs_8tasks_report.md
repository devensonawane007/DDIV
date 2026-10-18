# DDIV Phase 8.4: Eight-Task QuixBugs Local-Only Repair Benchmark Report

**Execution Date:** 2026-10-16T04:22:28Z  
**Tasks Evaluated:** 8 screened QuixBugs tasks  
**Model:** `qwen2.5-coder:7b` (Local Ollama: `http://localhost:11434`)  
**Total Benchmark Latency:** 506.24s  
**Output Directory:** `D:\PROJECTS\DDIV\results\quixbugs_benchmark_8tasks_20261016T084000Z`  

---

## 1. Aggregate Condition Comparison

| Condition | Planned Runs | Resolved | Resolution Rate (%) | Total Tokens | Mean Tokens/Task | Total Runtime |
| :--- | :-: | :-: | :-: | :-: | :-: | :-: |
| **BASELINE** | 8 | 5 | **62.5%** | 14165 | 1770 | 133.49s |
| **RETRY_ONLY** | 8 | 6 | **75.0%** | 24533 | 3066 | 178.06s |
| **FULL_DDIV** | 8 | 6 | **75.0%** | 24936 | 3117 | 178.08s |

---

## 2. Per-Task Resolution Breakdown

| Task ID | Program | BASELINE (1 att) | RETRY_ONLY (<=3 att) | FULL_DDIV (<=3 att) |
| :--- | :--- | :---: | :---: | :---: |
| `quixbugs-python-bucketsort` | `bucketsort` | **PASS** (1) | **PASS** (1) | **PASS** (1) |
| `quixbugs-python-flatten` | `flatten` | **PASS** (1) | **PASS** (1) | **PASS** (1) |
| `quixbugs-python-is_valid_parenthesization` | `is_valid_parenthesization` | FAIL (1) | **PASS** (2) | **PASS** (2) |
| `quixbugs-python-max_sublist_sum` | `max_sublist_sum` | **PASS** (1) | **PASS** (1) | **PASS** (1) |
| `quixbugs-python-pascal` | `pascal` | **PASS** (1) | **PASS** (1) | **PASS** (1) |
| `quixbugs-python-quicksort` | `quicksort` | FAIL (1) | FAIL (3) | FAIL (3) |
| `quixbugs-python-rpn_eval` | `rpn_eval` | FAIL (1) | FAIL (3) | FAIL (3) |
| `quixbugs-python-to_base` | `to_base` | **PASS** (1) | **PASS** (1) | **PASS** (1) |

---

## 3. Ground-Truth Isolation & Safety Compliance
- **Zero Cloud Inference API Calls:** All model generation was executed 100% locally via Ollama.
- **Zero Information Leakage:** Candidate agent workspaces contained exclusively target python programs; all tests, fixtures, and JSON oracles remained restricted to the evaluator side.
- **Sanitized Diagnostics:** All test outputs redacted expected oracle values (`[ORACLE_REDACTED]`).
- **Production State Protected:** `data/ddiv_memory.db` and SWE-bench historical results remained completely untouched.
- **Isolated Benchmark Memory:** All episodic memory records were written strictly to `quixbugs_8tasks_memory.db`.