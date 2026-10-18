# DDIV Ranked Shortlist of Additional SWE-bench Candidates

**Audit Timestamp:** 2026-10-16T04:35:00Z  
**Pool Source:** `D:/DDIV/data/swebench/test-00000-of-00001.parquet` (500 rows, 461 unverified remaining)  
**Safety Notice:** Scores and rankings below are **heuristic static estimates**, not empirical verification. No candidate is marked verified until isolated checkout, dependency provisioning, and test execution succeed.

---

## 1. Selection Methodology & Ranking Criteria

Candidates were evaluated across five static dimensions:
1. **Repository Track Record:** Prefer repositories already proven reproducible in DDIV on Windows (`mwaskom/seaborn`, `sympy/sympy`, `psf/requests`, `pylint-dev/pylint`).
2. **Defect & Target Test Granularity:** Strongly prefer tasks with exactly **1 single `FAIL_TO_PASS` test** and concise test patches to minimize test fixture overhead.
3. **Absence of Native / Heavy Infrastructure:** Exclude tasks requiring C/Cython compilation (`matplotlib`, `scikit-learn`, `astropy`) or running daemons (Postgres, MySQL, Redis, Memcached).
4. **Python 3.11 Standard Library Compatibility:** Prioritize modern package releases ($\ge 2021$) to avoid deprecated/removed APIs (`inspect.formatargspec`, `cgi`, `py._path`).
5. **Diversity:** Maximize representation across functional domains (data visualization, symbolic computation, data manipulation, web protocols, and template parsing).

---

## 2. Ranked Shortlist (25 Candidates)

| Rank | Task ID | Repository | Version | Base Commit | Target Test Count | Estimated Setup Complexity | Static Score (0-10) | Current Evidence Status |
|---|---|---|---|---|---|---|---|---|
| **1** | `mwaskom__seaborn-3069` | `mwaskom/seaborn` | `0.12` | `54cab15bdacf` | 2 | Low | 9.0 (Est.) | `STATIC_PROMISING` |
| **2** | `sympy__sympy-21847` | `sympy/sympy` | `1.9` | `d9b18c518d64` | 1 | Low | 9.0 (Est.) | `STATIC_PROMISING` |
| **3** | `sympy__sympy-21612` | `sympy/sympy` | `1.9` | `b4777fdcef46` | 1 | Low | 9.0 (Est.) | `STATIC_PROMISING` |
| **4** | `sympy__sympy-21596` | `sympy/sympy` | `1.9` | `110997fe18b9` | 1 | Low | 9.0 (Est.) | `STATIC_PROMISING` |
| **5** | `sympy__sympy-21379` | `sympy/sympy` | `1.9` | `624217179aaf` | 1 | Low | 9.0 (Est.) | `STATIC_PROMISING` |
| **6** | `pydata__xarray-7233` | `pydata/xarray` | `2022.09` | `51d37d1be955` | 1 | Medium | 8.5 (Est.) | `STATIC_PROMISING` |
| **7** | `pydata__xarray-7229` | `pydata/xarray` | `2022.09` | `3aa75c8d00a4` | 1 | Medium | 8.5 (Est.) | `STATIC_PROMISING` |
| **8** | `pydata__xarray-6938` | `pydata/xarray` | `2022.06` | `c4e40d991c28` | 1 | Medium | 8.5 (Est.) | `STATIC_PROMISING` |
| **9** | `django__django-16485` | `django/django` | `5.0` | `39f83765e12b` | 1 | Low | 8.5 (Est.) | `STATIC_PROMISING` |
| **10** | `django__django-17029` | `django/django` | `5.0` | `953f29f700a6` | 1 | Low | 8.5 (Est.) | `STATIC_PROMISING` |
| **11** | `django__django-16819` | `django/django` | `5.0` | `0b0998dc151f` | 1 | Low | 8.5 (Est.) | `STATIC_PROMISING` |
| **12** | `django__django-16595` | `django/django` | `5.0` | `f9fe062de5fc` | 1 | Low | 8.5 (Est.) | `STATIC_PROMISING` |
| **13** | `psf__requests-1142` | `psf/requests` | `1.1` | `22623bd8c265` | 1 | Low | 8.0 (Est.) | `STATIC_PROMISING` |
| **14** | `sympy__sympy-20916` | `sympy/sympy` | `1.8` | `82298df6a514` | 1 | Low | 8.5 (Est.) | `STATIC_PROMISING` |
| **15** | `sympy__sympy-20801` | `sympy/sympy` | `1.8` | `e11d3fed7821` | 1 | Low | 8.5 (Est.) | `STATIC_PROMISING` |
| **16** | `sympy__sympy-20428` | `sympy/sympy` | `1.8` | `c0e85160406f` | 1 | Low | 8.5 (Est.) | `STATIC_PROMISING` |
| **17** | `sympy__sympy-19954` | `sympy/sympy` | `1.7` | `6f54459aa024` | 1 | Low | 8.0 (Est.) | `STATIC_PROMISING` |
| **18** | `sympy__sympy-19346` | `sympy/sympy` | `1.7` | `94fb720696f5` | 1 | Low | 8.0 (Est.) | `STATIC_PROMISING` |
| **19** | `sympy__sympy-20590` | `sympy/sympy` | `1.7` | `cffd4e0f86fe` | 1 | Low | 8.0 (Est.) | `STATIC_PROMISING` |
| **20** | `sympy__sympy-19495` | `sympy/sympy` | `1.7` | `25fbcce5b1a4` | 1 | Low | 8.0 (Est.) | `STATIC_PROMISING` |
| **21** | `sympy__sympy-19637` | `sympy/sympy` | `1.7` | `63f8f465d485` | 1 | Low | 8.0 (Est.) | `STATIC_PROMISING` |
| **22** | `sphinx-doc__sphinx-10673` | `sphinx-doc/sphinx` | `5.2` | `f35d2a6cc726` | 1 | Medium | 8.0 (Est.) | `STATIC_PROMISING` |
| **23** | `sphinx-doc__sphinx-10449` | `sphinx-doc/sphinx` | `5.1` | `36367765fe78` | 1 | Medium | 8.0 (Est.) | `STATIC_PROMISING` |
| **24** | `sphinx-doc__sphinx-10435` | `sphinx-doc/sphinx` | `5.0` | `f1061c012e21` | 1 | Medium | 8.0 (Est.) | `STATIC_PROMISING` |
| **25** | `pydata__xarray-6721` | `pydata/xarray` | `2022.06` | `cc183652bf6e` | 1 | Medium | 8.0 (Est.) | `STATIC_PROMISING` |

---

## 3. Candidate Profiles and Compatibility Rationales

### 1. `mwaskom__seaborn-3069`
- **Repository:** `mwaskom/seaborn` (v0.12)
- **Base Commit:** `54cab15bdacf6a237fa364024ec442b0c3674643`
- **Target Tests:**
  - `tests/_core/test_plot.py::TestScaling::test_nominal_x_axis_tweaks`
  - `tests/_core/test_plot.py::TestScaling::test_nominal_y_axis_tweaks`
- **Compatibility Rationale:** Seaborn v0.12 is already proven in our four-task frozen benchmark (`mwaskom__seaborn-3187`). Pure Python library on top of matplotlib and pandas.
- **Estimated Setup:** Low. Fresh git clone, editable install (`pip install -e .`), execution via `pytest tests/_core/test_plot.py`.
- **Likely Blockers:** None anticipated; matplotlib backend should use `agg` to prevent headless GUI popups.

### 2. `sympy__sympy-21847`
- **Repository:** `sympy/sympy` (v1.9)
- **Base Commit:** `d9b18c518d648beff9e1be4b00e84d41eb311140`
- **Target Test:** `test_monomials` (located in `sympy/polys/tests/test_monomials.py`)
- **Compatibility Rationale:** Pure Python symbolic math library. Sympy 1.9 was released in 2021 and has excellent Python 3.11 compatibility. Polynomial algorithms have zero external dependencies beyond `mpmath`.
- **Estimated Setup:** Low. Editable install (`pip install -e .`), execution via `pytest sympy/polys/tests/test_monomials.py -k test_monomials`.
- **Likely Blockers:** None.

### 3. `sympy__sympy-21612`
- **Repository:** `sympy/sympy` (v1.9)
- **Base Commit:** `b4777fdcef468f3a8b417e1329c31405e4fb90be`
- **Target Test:** `test_Mul` (in `sympy/core/tests/test_expr.py`)
- **Compatibility Rationale:** Core expression manipulation; zero external library dependencies. Fast unit test execution ($< 2$ seconds).
- **Estimated Setup:** Low. Standard Sympy editable install.
- **Likely Blockers:** None.

### 4. `sympy__sympy-21596`
- **Repository:** `sympy/sympy` (v1.9)
- **Base Commit:** `110997fe18b950005a305943eb3c1a853e34b9d5`
- **Target Test:** `test_imageset_intersect_real` (in `sympy/sets/tests/test_fancysets.py`)
- **Compatibility Rationale:** Sets and number theory logic; deterministic and self-contained.
- **Estimated Setup:** Low.
- **Likely Blockers:** None.

### 5. `sympy__sympy-21379`
- **Repository:** `sympy/sympy` (v1.9)
- **Base Commit:** `624217179aaf978ea9f758f84443a6d482a514d3`
- **Target Test:** `test_Mod` (in `sympy/core/tests/test_numbers.py`)
- **Compatibility Rationale:** Number evaluation and modulo arithmetic. Fast execution.
- **Estimated Setup:** Low.
- **Likely Blockers:** None.

### 6. `pydata__xarray-7233`
- **Repository:** `pydata/xarray` (v2022.09)
- **Base Commit:** `51d37d1be9553b59f3e498679f220359aa6b71f3`
- **Target Test:** `xarray/tests/test_coarsen.py::TestCoarsenConstruct::test_coarsen_construct_keeps_all_coords`
- **Compatibility Rationale:** Modern xarray release from late 2022. Operates entirely on top of numpy and pandas, both of which are present in the host environment.
- **Estimated Setup:** Medium. Requires `numpy`, `pandas`, and `packaging` in isolated venv.
- **Likely Blockers:** Potential incompatibility with numpy 2.x if older C-APIs are touched; requires checking numpy version constraint in `setup.cfg`.

### 7. `django__django-16485`
- **Repository:** `django/django` (v5.0)
- **Base Commit:** `39f83765e12b704c32b9048a12e2307aa5231cbf`
- **Target Test:** `test_zero_values (template_tests.filter_tests.test_floatformat.FunctionTests.test_zero_values)`
- **Compatibility Rationale:** Pure template engine unit test (`floatformat` filter). Requires **zero** database connection, migration, or external database backend (Postgres/MySQL). Django 5.0 was built natively for Python 3.10–3.12.
- **Estimated Setup:** Low. `pip install -e .` and invoke via `python tests/runtests.py template_tests.filter_tests.test_floatformat`.
- **Likely Blockers:** Django test runner invocation differences vs standard pytest.

### 8. `django__django-17029`
- **Repository:** `django/django` (v5.0)
- **Base Commit:** `953f29f700a6534be5cfc9b4e5482e4e137145e1`
- **Target Test:** `test_clear_cache (apps.tests.AppsTests.test_clear_cache)`
- **Compatibility Rationale:** Core application registry and cache clearing logic. Self-contained in memory without database dependencies.
- **Estimated Setup:** Low. Standard Django test runner.
- **Likely Blockers:** None.

### 9. `django__django-16819`
- **Repository:** `django/django` (v5.0)
- **Base Commit:** `0b0998dc151f89db8e3100be05ec4cf5e062eb82`
- **Target Test:** `test_add_remove_index (migrations.test_optimizer.OptimizerTests.test_add_remove_index)`
- **Compatibility Rationale:** Migration optimizer graph reduction logic; pure Python data structure manipulation without schema alterations on disk.
- **Estimated Setup:** Low.
- **Likely Blockers:** None.

### 10. `psf__requests-1142`
- **Repository:** `psf/requests` (v1.1)
- **Base Commit:** `22623bd8c265e3176690cf85150937a4b0878d65`
- **Target Test:** `test_requests.py::RequestsTestCase::test_no_content_length`
- **Compatibility Rationale:** Minimal unit test on request header handling.
- **Estimated Setup:** Low.
- **Likely Blockers:** Very old release (v1.1, ~2013); potential syntax or urllib3 bundling quirks on Python 3.11.
