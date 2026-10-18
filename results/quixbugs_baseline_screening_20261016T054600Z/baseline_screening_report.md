# QuixBugs Phase 8.2: Baseline Defect Screening Report

**Screening Date:** 2026-10-16T00:19:09Z  
**Dataset Location:** `D:/PROJECTS/DDIV/data/quixbugs`  
**Total Screened:** 8 tasks  
**Eligible Tasks (Defect Reproduced):** 8  
**Ineligible Tasks:** 0  
**Environment / Recheck Needed:** 0  
**Screening Runtime:** 12.404 seconds  

---

## 1. Summary of Baseline Screening Results

| # | Task ID | Program | Total Tests | Failed Tests | Status | Duration |
| :-: | :--- | :--- | :-: | :-: | :-: | :-: |
| 1 | `quixbugs-python-bucketsort` | `bucketsort` | 1 | 1 | **`ELIGIBLE`** | 1.72s |
| 2 | `quixbugs-python-flatten` | `flatten` | 1 | 1 | **`ELIGIBLE`** | 1.48s |
| 3 | `quixbugs-python-is_valid_parenthesization` | `is_valid_parenthesization` | 1 | 1 | **`ELIGIBLE`** | 1.33s |
| 4 | `quixbugs-python-max_sublist_sum` | `max_sublist_sum` | 1 | 1 | **`ELIGIBLE`** | 1.62s |
| 5 | `quixbugs-python-pascal` | `pascal` | 1 | 1 | **`ELIGIBLE`** | 1.53s |
| 6 | `quixbugs-python-quicksort` | `quicksort` | 1 | 1 | **`ELIGIBLE`** | 1.50s |
| 7 | `quixbugs-python-rpn_eval` | `rpn_eval` | 1 | 1 | **`ELIGIBLE`** | 1.39s |
| 8 | `quixbugs-python-to_base` | `to_base` | 1 | 1 | **`ELIGIBLE`** | 1.72s |

---

## 2. Detailed Task Breakdown

### 2.1 quixbugs-python-bucketsort
- **Target File:** `python_programs/bucketsort.py`
- **Test File:** `python_testcases/test_bucketsort.py`
- **Eligibility Verdict:** **`ELIGIBLE`**
- **Defect Reproduced:** `True`
- **Environment Errors:** `False`
- **Failed Test Cases (1):**
  - `::test_bucketsort[case]`

### 2.2 quixbugs-python-flatten
- **Target File:** `python_programs/flatten.py`
- **Test File:** `python_testcases/test_flatten.py`
- **Eligibility Verdict:** **`ELIGIBLE`**
- **Defect Reproduced:** `True`
- **Environment Errors:** `False`
- **Failed Test Cases (1):**
  - `::test_flatten[case]`

### 2.3 quixbugs-python-is_valid_parenthesization
- **Target File:** `python_programs/is_valid_parenthesization.py`
- **Test File:** `python_testcases/test_is_valid_parenthesization.py`
- **Eligibility Verdict:** **`ELIGIBLE`**
- **Defect Reproduced:** `True`
- **Environment Errors:** `False`
- **Failed Test Cases (1):**
  - `::test_is_valid_parenthesization[case]`

### 2.4 quixbugs-python-max_sublist_sum
- **Target File:** `python_programs/max_sublist_sum.py`
- **Test File:** `python_testcases/test_max_sublist_sum.py`
- **Eligibility Verdict:** **`ELIGIBLE`**
- **Defect Reproduced:** `True`
- **Environment Errors:** `False`
- **Failed Test Cases (1):**
  - `::test_max_sublist_sum[case]`

### 2.5 quixbugs-python-pascal
- **Target File:** `python_programs/pascal.py`
- **Test File:** `python_testcases/test_pascal.py`
- **Eligibility Verdict:** **`ELIGIBLE`**
- **Defect Reproduced:** `True`
- **Environment Errors:** `False`
- **Failed Test Cases (1):**
  - `::test_pascal[case]`

### 2.6 quixbugs-python-quicksort
- **Target File:** `python_programs/quicksort.py`
- **Test File:** `python_testcases/test_quicksort.py`
- **Eligibility Verdict:** **`ELIGIBLE`**
- **Defect Reproduced:** `True`
- **Environment Errors:** `False`
- **Failed Test Cases (1):**
  - `::test_quicksort[case]`

### 2.7 quixbugs-python-rpn_eval
- **Target File:** `python_programs/rpn_eval.py`
- **Test File:** `python_testcases/test_rpn_eval.py`
- **Eligibility Verdict:** **`ELIGIBLE`**
- **Defect Reproduced:** `True`
- **Environment Errors:** `False`
- **Failed Test Cases (1):**
  - `::test_rpn_eval[case]`

### 2.8 quixbugs-python-to_base
- **Target File:** `python_programs/to_base.py`
- **Test File:** `python_testcases/test_to_base.py`
- **Eligibility Verdict:** **`ELIGIBLE`**
- **Defect Reproduced:** `True`
- **Environment Errors:** `False`
- **Failed Test Cases (1):**
  - `::test_to_base[case]`

---

## 3. Strict Research Constraints Adherence
- **Zero LLM / Inference API Calls:** All baseline runs executed using local Python and pytest.
- **Zero Repair Experiments Launched:** No candidate patches or model generations were requested.
- **Historical Data Untouched:** SWE-bench results and `data/ddiv_memory.db` remain unaltered.
- **Ground-Truth Isolation:** Execution used temporary isolated workspaces with complete test/JSON exclusion and sanitized diagnostic outputs.

## 4. Conclusion & Readiness for Repair Evaluation
All 8 selected tasks have verified defect reproduction under authoritative test suites without environment errors. They are confirmed eligible for Phase 8.3 repair experiments.