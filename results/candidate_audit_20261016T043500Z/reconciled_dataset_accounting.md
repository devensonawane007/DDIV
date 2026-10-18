# DDIV Reconciled Dataset Accounting Report

**Audit Timestamp:** 2026-10-16T04:35:00Z  
**Audited Artifacts Directory:** `D:/DDIV/results/candidate_screening_20261015T144611Z/`  
**Dataset Path:** `D:/DDIV/data/swebench/test-00000-of-00001.parquet`  
**Host Platform:** Windows 10/11, Python 3.11.9, pandas 2.3.2, pyarrow 23.0.0 (No Docker daemon active)

---

## 1. Executive Accounting Summary

| Metric | Historical Report Value | Audited & Verified Value | Status / Resolution |
|---|---|---|---|
| **Total Parquet Rows** | 500 | **500** | Verified exact match |
| **Unique `instance_id`s in Dataset** | 500 (implied) | **500** | 100% unique (no duplicates in parquet) |
| **Historical Exclusion List Size** | 32 | **32** | Defined in `EXISTING_BENCHMARK_TASKS` |
| **Excluded Tasks Present in Dataset** | 32 (reported) | **30** | **Discrepancy Root Cause Identified** |
| **Excluded Tasks Absent from Dataset** | 0 (assumed) | **2** | `psf__requests-2148`, `pytest-dev__pytest-5221` |
| **Actual Rows Excluded from Dataset** | 32 (reported) | **30** | $500 - 30 = 470$ |
| **Total Candidates Screened** | 470 | **470** | Mechanically correct ($500 - 30$) |
| **Statically Promising Candidates** | 424 (330 with score $\ge 6$) | **424** (330 with score $\ge 6$) | Verified exact match |
| **Statically Blocked Candidates** | 34 | **34** | Verified exact match |
| **Statically Ineligible Candidates** | 12 | **12** | Verified exact match |
| **Empirically Checked Tasks** | 9 | **9** | Verified exact match across 2 phases |
| **Verified Eligible Tasks** | 4 | **4** | Complete log trail and confirmed defect |
| **Blocked / Needs Recheck** | 5 | **5** (4 Blocked, 1 Needs Recheck) | Confirmed by raw logs |

---

## 2. Mathematical Reconciliation of the "500 − 32 = 468 vs. 470" Discrepancy

### 2.1 The Issue
The header of `D:/DDIV/results/candidate_screening_20261015T144611Z/candidate_screening_report.md` states:
```text
Total rows: 500 | Already excluded: 32 | Screened: 470
```
However, arithmetic requires:
$$500 - 32 = 468 \neq 470$$

### 2.2 Root Cause Analysis
During Phase 2 static screening (`scratch/phase1_2_screen.py`), the exclusion set was populated with 32 task identifiers derived from historical manifests (`benchmark_v2_tasks.json`, `select_pilot5.py`, and the frozen 4-task benchmark):
1. `astropy__astropy-12907`
2. `astropy__astropy-13033`
3. `astropy__astropy-14508`
4. `astropy__astropy-8872`
5. `django__django-11141`
6. `django__django-16429`
7. `matplotlib__matplotlib-20676`
8. `matplotlib__matplotlib-26342`
9. `mwaskom__seaborn-3187`
10. `pallets__flask-5014`
11. `psf__requests-2148`
12. `psf__requests-2931`
13. `pydata__xarray-4966`
14. `pydata__xarray-7393`
15. `pylint-dev__pylint-4970`
16. `pylint-dev__pylint-6903`
17. `pytest-dev__pytest-5221`
18. `pytest-dev__pytest-7982`
19. `pytest-dev__pytest-8399`
20. `scikit-learn__scikit-learn-13496`
21. `scikit-learn__scikit-learn-26323`
22. `sphinx-doc__sphinx-8269`
23. `sphinx-doc__sphinx-8638`
24. `sympy__sympy-13878`
25. `sympy__sympy-22914`
26. `sympy__sympy-23262`
27. `sympy__sympy-23413`
28. `sympy__sympy-23950`
29. `sympy__sympy-24443`
30. `sympy__sympy-24539`
31. `sympy__sympy-24562`
32. `sympy__sympy-24661`

When cross-referenced against `data/swebench/test-00000-of-00001.parquet` (which contains SWE-bench Verified tasks):
- **30 task IDs** are present in the dataset and were successfully filtered out.
- **2 task IDs** are **NOT present** in this 500-row parquet file:
  - `psf__requests-2148`
  - `pytest-dev__pytest-5221`
  *(Note: These tasks were present in earlier SWE-bench iterations or validation pilots, but were not selected into the official 500-task SWE-bench Verified test split).*

### 2.3 Mathematical Proof of Consistency
- Total rows in dataset: $500$
- In-dataset excluded duplicates: $30$
- Screened candidates: $500 - 30 = 470$
- In `phase1_2_summary.json`:
  ```json
  "total_rows": 500,
  "excluded_existing_tasks": 30,
  "candidates_screened": 470
  ```
- In the final report generation script (`scratch/phase5_report.py`), line 283 interpolated `len(EXISTING_TASKS)` (32) instead of `phase12['excluded_existing_tasks']` (30).
- Furthermore, in `candidate_screening_results.csv`, all 32 tasks were appended as `duplicate`. For the 2 non-dataset tasks, their repository column was appropriately blank `""` because no matching row existed in the parquet file.

**Conclusion:** The screened count of **470** is mathematically and mechanically accurate. The label "Already excluded: 32" was a reporting artifact reflecting the cardinality of the filter set rather than the number of dataset rows matched.

---

## 3. Dataset Breakdown and Classification Distribution

### 3.1 Repository Distribution of the 500 Total Rows
1. `django/django`: 231 (46.2%)
2. `sympy/sympy`: 75 (15.0%)
3. `sphinx-doc/sphinx`: 44 (8.8%)
4. `matplotlib/matplotlib`: 34 (6.8%)
5. `scikit-learn/scikit-learn`: 32 (6.4%)
6. `astropy/astropy`: 22 (4.4%)
7. `pydata/xarray`: 22 (4.4%)
8. `pytest-dev/pytest`: 19 (3.8%)
9. `pylint-dev/pylint`: 10 (2.0%)
10. `psf/requests`: 8 (1.6%)
11. `mwaskom/seaborn`: 2 (0.4%)
12. `pallets/flask`: 1 (0.2%)

### 3.2 Candidate Classification Accounting (Total = 470)
- **`promising_not_verified`**: 424
  - Score $\ge 6/10$: **330**
  - Score 4–5/10: **94**
- **`blocked`**: 34
  - Blocked by Docker requirement keyword: 23
  - Blocked by external daemon dependencies (Redis/Postgres/MySQL): 7
  - Blocked by POSIX/Linux-only APIs (`/proc/`, `os.fork`): 4
- **`ineligible`**: 12
  - Missing test patch, missing `FAIL_TO_PASS`, or score $< 3$: 12
- **Sum**: $424 + 34 + 12 = 470$.

---

## 4. Empirical Verification Accounting (Total Checked = 9)

Across Phase 3 and Phase 3b, exactly 9 tasks were executed in isolated temporary workspaces with pytest:

| Task ID | Repo | Base Commit | Test Exit Code | Runtime | Audit Classification |
|---|---|---|---|---|---|
| `pylint-dev__pylint-6386` | `pylint-dev/pylint` | `754b487f4d89` | RC 1 (FAILED) | 2.89s | `VERIFIED_ELIGIBLE` |
| `pylint-dev__pylint-8898` | `pylint-dev/pylint` | `1f8c4d9eb185` | RC 1 (FAILED) | 2.41s | `VERIFIED_ELIGIBLE` |
| `psf__requests-5414` | `psf/requests` | `39d0fdd9096f` | RC 1 (FAILED) | 2.00s | `VERIFIED_ELIGIBLE` |
| `psf__requests-6028` | `psf/requests` | `0192aac24123` | RC 1 (FAILED) | 1.27s | `VERIFIED_ELIGIBLE` |
| `sphinx-doc__sphinx-10323` | `sphinx-doc/sphinx` | `31eba1a76dd4` | RC 0 (XFAIL) | 0.52s | `NEEDS_RECHECK` |
| `pylint-dev__pylint-4661` | `pylint-dev/pylint` | `1d1619ef913b` | RC 4 (ERROR) | 0.83s | `BLOCKED` |
| `pylint-dev__pylint-4604` | `pylint-dev/pylint` | `1e55ae64624d` | RC 4 (ERROR) | 1.16s | `BLOCKED` |
| `pylint-dev__pylint-7277` | `pylint-dev/pylint` | `684a1d6aa0a6` | RC 4 (ERROR) | 4.36s | `BLOCKED` |
| `sphinx-doc__sphinx-8721` | `sphinx-doc/sphinx` | `82ef497a8c88` | RC 1 (ERROR) | 2.02s | `BLOCKED` |

Accounting is now fully audited and reconciled.
