# DDIV Preflight Verification Plan (Proposed Batch 1)

**Date:** 2026-10-16T04:35:00Z  
**Target Output Directory:** `D:/DDIV/results/candidate_audit_20261016T043500Z/batch1_verification/`  
**Execution Status:** **PAUSED — PENDING USER APPROVAL**  
**Safety Gate:** In accordance with prompt instructions, **no verification tests will be executed until the user explicitly approves this plan.**

---

## 1. Candidate Batch Selection (5 Strongest Diverse Candidates)

We propose a balanced batch of 5 high-potential tasks spanning four distinct repositories:

| Batch # | Task ID | Repository | Version | Base Commit | Target Test Identifier(s) | Primary Domain |
|---|---|---|---|---|---|---|
| **B1-1** | `mwaskom__seaborn-3069` | `mwaskom/seaborn` | `0.12` | `54cab15bdacf` | `tests/_core/test_plot.py::TestScaling::test_nominal_x_axis_tweaks`<br>`tests/_core/test_plot.py::TestScaling::test_nominal_y_axis_tweaks` | Data Visualization |
| **B1-2** | `sympy__sympy-21847` | `sympy/sympy` | `1.9` | `d9b18c518d64` | `test_monomials` (in `sympy/polys/tests/test_monomials.py`) | Polynomial Algebra |
| **B1-3** | `sympy__sympy-21612` | `sympy/sympy` | `1.9` | `b4777fdcef46` | `test_Mul` (in `sympy/core/tests/test_expr.py`) | Symbolic Arithmetic |
| **B1-4** | `pydata__xarray-7233` | `pydata/xarray` | `2022.09` | `51d37d1be955` | `xarray/tests/test_coarsen.py::TestCoarsenConstruct::test_coarsen_construct_keeps_all_coords` | Multidimensional Arrays |
| **B1-5** | `django__django-16485` | `django/django` | `5.0` | `39f83765e12b` | `template_tests.filter_tests.test_floatformat.FunctionTests.test_zero_values` | Template Parsing (No DB) |

---

## 2. Preflight Audit Checklist per Candidate

### B1-1: `mwaskom__seaborn-3069`
- **Repository URL:** `https://github.com/mwaskom/seaborn.git`
- **Target Base Commit:** `54cab15bdacf6a237fa364024ec442b0c3674643`
- **Existing Evidence:**
  - `mwaskom__seaborn-3187` is already one of the 4 verified benchmark tasks in DDIV.
  - Seaborn 0.12 builds and runs cleanly on the host Windows Python 3.11 environment.
- **Required Packages & Cache Status:**
  - `pytest` (Installed: 7.4.4)
  - `numpy` (Installed: 2.2.6)
  - `pandas` (Installed: 2.3.2)
  - `matplotlib` (Installed: 3.10.8)
  - All prerequisites are already present in the local Python environment.
- **Exact Proposed Commands:**
  ```powershell
  # 1. Clone & checkout base
  git clone --quiet https://github.com/mwaskom/seaborn.git <temp_ws>/repo
  cd <temp_ws>/repo
  git checkout 54cab15bdacf6a237fa364024ec442b0c3674643

  # 2. Provision venv
  python -m venv <temp_ws>/venv --system-site-packages
  <temp_ws>/venv/Scripts/pip install -e . --no-deps

  # 3. Apply test patch only
  git apply --ignore-whitespace <test_patch_file>

  # 4. Collect & run target test
  <temp_ws>/venv/Scripts/python -m pytest --collect-only -q tests/_core/test_plot.py -k "test_nominal_x_axis_tweaks or test_nominal_y_axis_tweaks"
  <temp_ws>/venv/Scripts/python -m pytest -v --tb=short tests/_core/test_plot.py -k "test_nominal_x_axis_tweaks or test_nominal_y_axis_tweaks"
  ```
- **Expected Runtime:** $\approx 15\text{s}$ clone, $\approx 3\text{s}$ test run.
- **Expected Storage:** $\approx 80\text{ MB}$.

---

### B1-2: `sympy__sympy-21847`
- **Repository URL:** `https://github.com/sympy/sympy.git`
- **Target Base Commit:** `d9b18c518d648beff9e1be4b00e84d41eb311140`
- **Existing Evidence:**
  - `sympy__sympy-23413` is an active, verified DDIV benchmark task.
  - Pure Python library; zero native compilation.
- **Required Packages & Cache Status:**
  - `mpmath` (Installed: 1.3.0)
  - `pytest` (Installed: 7.4.4)
  - 100% locally cached / available.
- **Exact Proposed Commands:**
  ```powershell
  # 1. Clone & checkout
  git clone --quiet https://github.com/sympy/sympy.git <temp_ws>/repo
  cd <temp_ws>/repo
  git checkout d9b18c518d648beff9e1be4b00e84d41eb311140

  # 2. Provision venv
  python -m venv <temp_ws>/venv --system-site-packages
  <temp_ws>/venv/Scripts/pip install -e . --no-deps

  # 3. Apply test patch
  git apply --ignore-whitespace <test_patch_file>

  # 4. Collect & run
  <temp_ws>/venv/Scripts/python -m pytest --collect-only -q sympy/polys/tests/test_monomials.py -k test_monomials
  <temp_ws>/venv/Scripts/python -m pytest -v --tb=short sympy/polys/tests/test_monomials.py -k test_monomials
  ```
- **Expected Runtime:** $\approx 35\text{s}$ clone, $\approx 2\text{s}$ test run.
- **Expected Storage:** $\approx 150\text{ MB}$.

---

### B1-3: `sympy__sympy-21612`
- **Repository URL:** `https://github.com/sympy/sympy.git`
- **Target Base Commit:** `b4777fdcef468f3a8b417e1329c31405e4fb90be`
- **Existing Evidence:**
  - Standard Sympy core expression test (`test_Mul`).
- **Required Packages & Cache Status:**
  - `mpmath` (Installed: 1.3.0), `pytest` (Installed: 7.4.4).
- **Exact Proposed Commands:**
  ```powershell
  # 1. Clone & checkout
  git clone --quiet https://github.com/sympy/sympy.git <temp_ws>/repo
  cd <temp_ws>/repo
  git checkout b4777fdcef468f3a8b417e1329c31405e4fb90be

  # 2. Provision venv
  python -m venv <temp_ws>/venv --system-site-packages
  <temp_ws>/venv/Scripts/pip install -e . --no-deps

  # 3. Apply test patch
  git apply --ignore-whitespace <test_patch_file>

  # 4. Collect & run
  <temp_ws>/venv/Scripts/python -m pytest --collect-only -q sympy/core/tests/test_expr.py -k test_Mul
  <temp_ws>/venv/Scripts/python -m pytest -v --tb=short sympy/core/tests/test_expr.py -k test_Mul
  ```
- **Expected Runtime:** $\approx 35\text{s}$ clone, $\approx 2\text{s}$ test run.
- **Expected Storage:** $\approx 150\text{ MB}$.

---

### B1-4: `pydata__xarray-7233`
- **Repository URL:** `https://github.com/pydata/xarray.git`
- **Target Base Commit:** `51d37d1be9553b59f3e498679f220359aa6b71f3`
- **Existing Evidence:**
  - Modern 2022 release with pure Python multidimensional array logic.
- **Required Packages & Cache Status:**
  - `numpy` (Installed: 2.2.6), `pandas` (Installed: 2.3.2), `packaging` (Installed: 25.0).
- **Exact Proposed Commands:**
  ```powershell
  # 1. Clone & checkout
  git clone --quiet https://github.com/pydata/xarray.git <temp_ws>/repo
  cd <temp_ws>/repo
  git checkout 51d37d1be9553b59f3e498679f220359aa6b71f3

  # 2. Provision venv
  python -m venv <temp_ws>/venv --system-site-packages
  <temp_ws>/venv/Scripts/pip install -e . --no-deps

  # 3. Apply test patch
  git apply --ignore-whitespace <test_patch_file>

  # 4. Collect & run
  <temp_ws>/venv/Scripts/python -m pytest --collect-only -q xarray/tests/test_coarsen.py -k test_coarsen_construct_keeps_all_coords
  <temp_ws>/venv/Scripts/python -m pytest -v --tb=short xarray/tests/test_coarsen.py -k test_coarsen_construct_keeps_all_coords
  ```
- **Expected Runtime:** $\approx 20\text{s}$ clone, $\approx 3\text{s}$ test run.
- **Expected Storage:** $\approx 90\text{ MB}$.

---

### B1-5: `django__django-16485`
- **Repository URL:** `https://github.com/django/django.git`
- **Target Base Commit:** `39f83765e12b704c32b9048a12e2307aa5231cbf`
- **Existing Evidence:**
  - Zero database dependency; tests template filter `floatformat` on numeric inputs.
- **Required Packages & Cache Status:**
  - `asgiref`, `sqlparse` (Installed: 0.5.3), standard library.
- **Exact Proposed Commands:**
  ```powershell
  # 1. Clone & checkout
  git clone --quiet https://github.com/django/django.git <temp_ws>/repo
  cd <temp_ws>/repo
  git checkout 39f83765e12b704c32b9048a12e2307aa5231cbf

  # 2. Provision venv
  python -m venv <temp_ws>/venv --system-site-packages
  <temp_ws>/venv/Scripts/pip install -e . --no-deps

  # 3. Apply test patch
  git apply --ignore-whitespace <test_patch_file>

  # 4. Collect & run via Django test runner
  <temp_ws>/venv/Scripts/python tests/runtests.py template_tests.filter_tests.test_floatformat --verbosity=2 -k test_zero_values
  ```
- **Expected Runtime:** $\approx 45\text{s}$ clone, $\approx 2\text{s}$ test run.
- **Expected Storage:** $\approx 200\text{ MB}$.

---

## 3. Total Resource Estimates & Isolation Plan

- **Total Batch Disk Storage:** $\approx 670\text{ MB}$ (all allocated inside isolated `%TEMP%/ddiv_preflight_batch1/` and deleted immediately following execution).
- **Total Batch Execution Time:** $\approx 3.5$ minutes total (network clone dominated; test execution is $< 15$ seconds combined).
- **Log Archival:** All raw logs (`clone.log`, `checkout.log`, `patch_apply.log`, `collect.log`, `baseline_run.log`) will be saved directly into `D:/DDIV/results/candidate_audit_20261016T043500Z/batch1_verification/<task_id>/`.

---

## 4. Strict Safety & Research Integrity Affirmation

Prior to requesting approval, we affirm that:
1. **Zero Gold Patch Exposure:** Column `patch` from `test-00000-of-00001.parquet` will not be inspected, read, or applied.
2. **Zero Production State Alteration:** `data/ddiv_memory.db`, `evaluation/` codebase, `core/` codebase, frozen manifests (`demo_freeze_manifest.json`, `pilot_freeze_manifest.json`), and prior results directories will **not** be touched.
3. **Zero External API / LLM Calls:** No paid API keys or LLMs will be invoked.
4. **Isolated Workspaces:** All checkouts and executions are restricted to `%TEMP%`.
5. **No Automatic Execution:** Execution is **halted** now pending explicit user command.
