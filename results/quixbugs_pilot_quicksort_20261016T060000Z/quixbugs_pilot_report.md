# QuixBugs Single-Task Pilot Report: `quixbugs-python-quicksort`

**Execution Date:** 2026-10-16T02:10:18Z  
**Task:** `quixbugs-python-quicksort` (`python_programs/quicksort.py`)  
**Model:** `qwen2.5-coder:7b` (Local Ollama)  
**Output Directory:** `D:\PROJECTS\DDIV\results\quixbugs_pilot_quicksort_20261016T060000Z`  

---

## 1. Experimental Conditions Comparison

| Condition | Max Attempts | Attempts Used | Resolved? | Total Tokens | Latency (s) | Final Verdict |
| :--- | :-: | :-: | :-: | :-: | :-: | :--- |
| **BASELINE** | 1 | 1 | NO (FAIL) | 1763 | 13.77s | `UNRESOLVED (Tests failed)` |
| **RETRY_ONLY** | 3 | 3 | NO (FAIL) | 6419 | 50.34s | `UNRESOLVED (Syntax error)` |
| **FULL_DDIV** | 3 | 2 | **YES (PASS)** | 4100 | 26.33s | `RESOLVED` |

---

## 2. Condition Detail Breakdown

### 2.BASELINE
- **Condition:** `BASELINE`
- **Resolved:** `False`
- **Attempts Taken:** 1 / 1
- **Total Duration:** 13.769s
- **Token Accounting:** prompt=1554, completion=209, total=1763
- **Attempt Trace:**
  - Attempt 1: verdict=`UNRESOLVED (Tests failed)`, applied=True, failure=`ASSERTION_FAILURE`, duration=13.769s

### 2.RETRY_ONLY
- **Condition:** `RETRY_ONLY`
- **Resolved:** `False`
- **Attempts Taken:** 3 / 3
- **Total Duration:** 50.34s
- **Token Accounting:** prompt=5667, completion=752, total=6419
- **Attempt Trace:**
  - Attempt 1: verdict=`UNRESOLVED (Tests failed)`, applied=True, failure=`ASSERTION_FAILURE`, duration=13.738s
  - Attempt 2: verdict=`UNRESOLVED (Tests failed)`, applied=True, failure=`ASSERTION_FAILURE`, duration=15.798s
  - Attempt 3: verdict=`UNRESOLVED (Syntax error)`, applied=True, failure=`SYNTAX_ERROR`, duration=20.804s

### 2.FULL_DDIV
- **Condition:** `FULL_DDIV`
- **Resolved:** `True`
- **Attempts Taken:** 2 / 3
- **Total Duration:** 26.334s
- **Token Accounting:** prompt=3738, completion=362, total=4100
- **Attempt Trace:**
  - Attempt 1: verdict=`UNRESOLVED (Tests failed)`, applied=True, failure=`ASSERTION_FAILURE`, duration=13.593s
  - Attempt 2: verdict=`RESOLVED`, applied=True, failure=`NONE`, duration=12.726s

---

## 3. Ground-Truth Isolation & Safety Compliance
- **Zero Cloud Inference API Calls:** All inference executed locally against Ollama.
- **Zero Information Leakage:** Workspaces contained only `quicksort.py`; testcases and oracles remained strictly on evaluator side.
- **Sanitized Failure Diagnostics:** All test outputs redacted expected oracle values.
- **Untouched Production State:** `data/ddiv_memory.db` and SWE-bench historical results remained completely untouched.

## 4. Conclusion & Readiness for Full Benchmark
This single-task pilot validates the end-to-end repair flow for QuixBugs using smaller local models. 
The system is now prepared for multi-task benchmark expansion.