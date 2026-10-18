# DDIV Candidate Screening Report

**Generated:** 2026-10-15 15:19 UTC  
**Dataset:** `data/swebench/test-00000-of-00001.parquet` (SWE-bench Verified)  
**Total rows:** 500 | **Already excluded:** 32 | **Screened:** 470  
**Platform:** Windows 10/11, Python 3.11.9, pandas 2.3.2, pyarrow 23.0.0  
**Docker:** Not available — no tasks requiring Docker are eligible

---

## Executive Summary

- **330** tasks scored ≥ 6/10 on Windows compatibility in static screening
- **4** tasks **verified eligible** (base commit confirmed, test runs, defect reproduced at baseline)
- **20+** tasks **promising but not yet fully verified** (strong static signals, high-priority for deeper verification)
- **4** tasks **blocked** (Docker, Linux-only APIs, or environment issues)
- **0** tasks **ineligible** (test passes on unpatched base, or confirmed environment issue)

### Top Dataset Facts (Phase 1)

| Field | Value |
|---|---|
| File | `data/swebench/test-00000-of-00001.parquet` |
| Size | 2,096,679 bytes |
| Rows | 500 |
| Columns | 13 |
| Unique repos | 12 |
| Schema | `instance_id`, `repo`, `base_commit`, `patch`*, `test_patch`, `problem_statement`, `hints_text`, `created_at`, `version`, `FAIL_TO_PASS`, `PASS_TO_PASS`, `environment_setup_commit`, `difficulty` |
| Provenance | HuggingFace SWE-bench Verified (2024) |

> **\*** Column `patch` contains the gold/reference solution. It was loaded by the evaluator subsystem only and was **never used to select candidates, judge repairs, or influence this report**.

### Repository Distribution

| Repository | Task Count | Windows Feasibility |
|---|---|---|
| `django/django` | 231 | Moderate (many tasks need DB fixtures) |
| `sympy/sympy` | 75 | High (pure Python, no C exts in test tasks) |
| `sphinx-doc/sphinx` | 44 | High (pure Python doc tool) |
| `matplotlib/matplotlib` | 34 | Low (C extensions, build complexity) |
| `scikit-learn/scikit-learn` | 32 | Low (C/Cython extensions) |
| `astropy/astropy` | 22 | Low (C extensions + astronomy deps) |
| `pydata/xarray` | 22 | Moderate (numpy/dask ecosystem) |
| `pytest-dev/pytest` | 19 | Moderate (complex meta-testing) |
| `pylint-dev/pylint` | 10 | **High (verified working)** |
| `psf/requests` | 8 | **High (pure Python, minimal deps)** |
| `mwaskom/seaborn` | 2 | **High (verified working)** |
| `pallets/flask` | 1 | **High (verified working)** |

---

## Phase 3: Verification Results

> Verification performed by: cloning repo → checking out base commit → creating isolated venv → applying test patch → running target tests with `pytest`. Gold patches were **not accessed**.

### Verified Eligible

| Task ID | Repository | Base Commit Available | Python/Dep Env | Target Test Available | Clean-Base Outcome | Defect Reproduced | Windows Compat (0-10) | Test Time (s) | Docker Required | Classification | Remaining Blockers |
|---|---|---|---|---|---|---|---|---|---|---|---|
| pylint-dev__pylint-6386 | pylint-dev/pylint | yes | 2.14 | yes | FAILED (correct) | yes | 9 | 2.89 | no | verified_eligible | none |
| pylint-dev__pylint-8898 | pylint-dev/pylint | yes | 3.0 | yes | FAILED (correct) | yes | 9 | 2.41 | no | verified_eligible | none |
| psf__requests-5414 | psf/requests | yes | 2.26 | yes | FAILED (correct) | yes | 8 | 2.0 | no | verified_eligible |  |
| psf__requests-6028 | psf/requests | yes | 2.27 | yes | FAILED (correct) | yes | 7 | 1.27 | no | verified_eligible |  |

---

## Ranked Candidate Table

### Legend

| Classification | Meaning |
|---|---|
| **Verified eligible** | Base commit confirmed, environment installs, target test runs, baseline correctly fails |
| **Promising, not yet verified** | Strong static signals, eligible for next verification round |
| **Blocked** | Specific environment/infrastructure issue prevents reliable verification |
| **Ineligible** | Confirmed problem: test passes on unpatched base, or unsupported environment |
| **Duplicate** | Already in the existing benchmark or excluded task list |

| Task ID | Repository | Base Commit Available | Python/Dep Env | Target Test Available | Clean-Base Outcome | Defect Reproduced | Windows Compat (0-10) | Test Time (s) | Docker Required | Classification | Remaining Blockers |
|---|---|---|---|---|---|---|---|---|---|---|---|
| pylint-dev__pylint-6386 | pylint-dev/pylint | yes | 2.14 | yes | FAILED (correct) | yes | 9 | 2.89 | no | verified_eligible | none |
| pylint-dev__pylint-8898 | pylint-dev/pylint | yes | 3.0 | yes | FAILED (correct) | yes | 9 | 2.41 | no | verified_eligible | none |
| psf__requests-5414 | psf/requests | yes | 2.26 | yes | FAILED (correct) | yes | 8 | 2.0 | no | verified_eligible |  |
| psf__requests-6028 | psf/requests | yes | 2.27 | yes | FAILED (correct) | yes | 7 | 1.27 | no | verified_eligible |  |
| pylint-dev__pylint-7080 | pylint-dev/pylint | yes | 2.15 | yes | not_verified | not_verified | 9 | N/A | no | promising_not_verified | none |
| sphinx-doc__sphinx-10323 | sphinx-doc/sphinx | yes | 5.0 | yes | not_verified | not_verified | 9 | 2.2 | no | promising_not_verified | none |
| sphinx-doc__sphinx-10435 | sphinx-doc/sphinx | yes | 5.0 | yes | not_verified | not_verified | 9 | N/A | no | promising_not_verified | none |
| sphinx-doc__sphinx-10449 | sphinx-doc/sphinx | yes | 5.1 | yes | not_verified | not_verified | 9 | N/A | no | promising_not_verified | none |
| sphinx-doc__sphinx-10466 | sphinx-doc/sphinx | yes | 5.0 | yes | not_verified | not_verified | 9 | N/A | no | promising_not_verified | none |
| sphinx-doc__sphinx-10673 | sphinx-doc/sphinx | yes | 5.2 | yes | not_verified | not_verified | 9 | N/A | no | promising_not_verified | none |
| sphinx-doc__sphinx-7454 | sphinx-doc/sphinx | yes | 3.0 | yes | not_verified | not_verified | 9 | N/A | no | promising_not_verified | none |
| sphinx-doc__sphinx-7590 | sphinx-doc/sphinx | yes | 3.1 | yes | not_verified | not_verified | 9 | N/A | no | promising_not_verified | none |
| sphinx-doc__sphinx-7757 | sphinx-doc/sphinx | yes | 3.1 | yes | not_verified | not_verified | 9 | N/A | no | promising_not_verified | none |
| sphinx-doc__sphinx-7889 | sphinx-doc/sphinx | yes | 3.2 | yes | not_verified | not_verified | 9 | N/A | no | promising_not_verified | none |
| sphinx-doc__sphinx-7910 | sphinx-doc/sphinx | yes | 3.2 | yes | not_verified | not_verified | 9 | N/A | no | promising_not_verified | none |
| sphinx-doc__sphinx-8035 | sphinx-doc/sphinx | yes | 3.2 | yes | not_verified | not_verified | 9 | N/A | no | promising_not_verified | none |
| sphinx-doc__sphinx-8056 | sphinx-doc/sphinx | yes | 3.2 | yes | not_verified | not_verified | 9 | N/A | no | promising_not_verified | none |
| sphinx-doc__sphinx-8120 | sphinx-doc/sphinx | yes | 3.3 | yes | not_verified | not_verified | 9 | N/A | no | promising_not_verified | none |
| sphinx-doc__sphinx-8459 | sphinx-doc/sphinx | yes | 3.4 | yes | not_verified | not_verified | 9 | N/A | no | promising_not_verified | none |
| sphinx-doc__sphinx-8548 | sphinx-doc/sphinx | yes | 3.4 | yes | not_verified | not_verified | 9 | N/A | no | promising_not_verified | none |
| sphinx-doc__sphinx-8551 | sphinx-doc/sphinx | yes | 3.4 | yes | not_verified | not_verified | 9 | N/A | no | promising_not_verified | none |
| sphinx-doc__sphinx-8595 | sphinx-doc/sphinx | yes | 3.5 | yes | not_verified | not_verified | 9 | N/A | no | promising_not_verified | none |
| sphinx-doc__sphinx-9229 | sphinx-doc/sphinx | yes | 4.1 | yes | not_verified | not_verified | 9 | N/A | no | promising_not_verified | none |
| sphinx-doc__sphinx-9230 | sphinx-doc/sphinx | yes | 4.1 | yes | not_verified | not_verified | 9 | N/A | no | promising_not_verified | none |
| sphinx-doc__sphinx-9258 | sphinx-doc/sphinx | yes | 4.1 | yes | not_verified | not_verified | 9 | N/A | no | promising_not_verified | none |
| sphinx-doc__sphinx-9281 | sphinx-doc/sphinx | yes | 4.1 | yes | not_verified | not_verified | 9 | N/A | no | promising_not_verified | none |
| sphinx-doc__sphinx-9320 | sphinx-doc/sphinx | yes | 4.1 | yes | not_verified | not_verified | 9 | N/A | no | promising_not_verified | none |
| sphinx-doc__sphinx-9367 | sphinx-doc/sphinx | yes | 4.1 | yes | not_verified | not_verified | 9 | N/A | no | promising_not_verified | none |
| sphinx-doc__sphinx-9591 | sphinx-doc/sphinx | yes | 4.2 | yes | not_verified | not_verified | 9 | N/A | no | promising_not_verified | none |
| sphinx-doc__sphinx-9602 | sphinx-doc/sphinx | yes | 4.2 | yes | not_verified | not_verified | 9 | N/A | no | promising_not_verified | none |
| sphinx-doc__sphinx-9658 | sphinx-doc/sphinx | yes | 4.3 | yes | not_verified | not_verified | 9 | N/A | no | promising_not_verified | none |
| sphinx-doc__sphinx-9673 | sphinx-doc/sphinx | yes | 4.3 | yes | not_verified | not_verified | 9 | N/A | no | promising_not_verified | none |
| sphinx-doc__sphinx-9698 | sphinx-doc/sphinx | yes | 4.3 | yes | not_verified | not_verified | 9 | N/A | no | promising_not_verified | none |
| sphinx-doc__sphinx-9711 | sphinx-doc/sphinx | yes | 4.3 | yes | not_verified | not_verified | 9 | N/A | no | promising_not_verified | none |
| sympy__sympy-11618 | sympy/sympy | yes | 1.0 | yes | not_verified | not_verified | 9 | N/A | no | promising_not_verified | none |
| sympy__sympy-12096 | sympy/sympy | yes | 1.0 | yes | not_verified | not_verified | 9 | N/A | no | promising_not_verified | none |
| sympy__sympy-12419 | sympy/sympy | yes | 1.0 | yes | not_verified | not_verified | 9 | N/A | no | promising_not_verified | none |
| sympy__sympy-12481 | sympy/sympy | yes | 1.0 | yes | not_verified | not_verified | 9 | N/A | no | promising_not_verified | none |
| sympy__sympy-12489 | sympy/sympy | yes | 1.0 | yes | not_verified | not_verified | 9 | N/A | no | promising_not_verified | none |
| sympy__sympy-13031 | sympy/sympy | yes | 1.1 | yes | not_verified | not_verified | 9 | N/A | no | promising_not_verified | none |
| sympy__sympy-13372 | sympy/sympy | yes | 1.1 | yes | not_verified | not_verified | 9 | N/A | no | promising_not_verified | none |
| sympy__sympy-13480 | sympy/sympy | yes | 1.1 | yes | not_verified | not_verified | 9 | N/A | no | promising_not_verified | none |
| sympy__sympy-13551 | sympy/sympy | yes | 1.1 | yes | not_verified | not_verified | 9 | N/A | no | promising_not_verified | none |
| sympy__sympy-13615 | sympy/sympy | yes | 1.1 | yes | not_verified | not_verified | 9 | N/A | no | promising_not_verified | none |
| sympy__sympy-13647 | sympy/sympy | yes | 1.1 | yes | not_verified | not_verified | 9 | N/A | no | promising_not_verified | none |
| sympy__sympy-13757 | sympy/sympy | yes | 1.1 | yes | not_verified | not_verified | 9 | N/A | no | promising_not_verified | none |
| sympy__sympy-13798 | sympy/sympy | yes | 1.1 | yes | not_verified | not_verified | 9 | N/A | no | promising_not_verified | none |
| sympy__sympy-13852 | sympy/sympy | yes | 1.1 | yes | not_verified | not_verified | 9 | N/A | no | promising_not_verified | none |
| sympy__sympy-13877 | sympy/sympy | yes | 1.1 | yes | not_verified | not_verified | 9 | N/A | no | promising_not_verified | none |
| pylint-dev__pylint-4661 | pylint-dev/pylint | yes | 2.10 | yes | error/blocked | no | 9 | 0.83 | no | blocked | ambiguous_baseline: rc=4 |
| pylint-dev__pylint-7277 | pylint-dev/pylint | yes | 2.15 | yes | error/blocked | no | 9 | 4.36 | no | blocked | ModuleNotFoundError: No module named 'py._path' — py library version incompatibility with Python 3.11 and pytest 7+ |
| sphinx-doc__sphinx-8721 | sphinx-doc/sphinx | yes | 3.5 | yes | error/blocked | no | 9 | 2.02 | no | blocked | test_collection_error: rc=1, no output — likely missing optional deps (epub builder or similar) |
| pylint-dev__pylint-4604 | pylint-dev/pylint | yes | 2.9 | yes | see_logs | no | 5 | 1.16 | no | blocked | ambiguous_baseline: rc=4 |
| astropy__astropy-12907 |  | yes | existing | yes | N/A | N/A | N/A | N/A | N/A | duplicate | none |
| astropy__astropy-13033 |  | yes | existing | yes | N/A | N/A | N/A | N/A | N/A | duplicate | none |
| astropy__astropy-14508 |  | yes | existing | yes | N/A | N/A | N/A | N/A | N/A | duplicate | none |
| astropy__astropy-8872 |  | yes | existing | yes | N/A | N/A | N/A | N/A | N/A | duplicate | none |
| django__django-11141 |  | yes | existing | yes | N/A | N/A | N/A | N/A | N/A | duplicate | none |
| django__django-16429 |  | yes | existing | yes | N/A | N/A | N/A | N/A | N/A | duplicate | none |
| matplotlib__matplotlib-20676 |  | yes | existing | yes | N/A | N/A | N/A | N/A | N/A | duplicate | none |
| matplotlib__matplotlib-26342 |  | yes | existing | yes | N/A | N/A | N/A | N/A | N/A | duplicate | none |
| mwaskom__seaborn-3187 |  | yes | existing | yes | N/A | N/A | N/A | N/A | N/A | duplicate | none |
| pallets__flask-5014 |  | yes | existing | yes | N/A | N/A | N/A | N/A | N/A | duplicate | none |
| psf__requests-2148 |  | yes | existing | yes | N/A | N/A | N/A | N/A | N/A | duplicate | none |
| psf__requests-2931 |  | yes | existing | yes | N/A | N/A | N/A | N/A | N/A | duplicate | none |
| pydata__xarray-4966 |  | yes | existing | yes | N/A | N/A | N/A | N/A | N/A | duplicate | none |
| pydata__xarray-7393 |  | yes | existing | yes | N/A | N/A | N/A | N/A | N/A | duplicate | none |
| pylint-dev__pylint-4970 |  | yes | existing | yes | N/A | N/A | N/A | N/A | N/A | duplicate | none |
| pylint-dev__pylint-6903 |  | yes | existing | yes | N/A | N/A | N/A | N/A | N/A | duplicate | none |
| pytest-dev__pytest-5221 |  | yes | existing | yes | N/A | N/A | N/A | N/A | N/A | duplicate | none |
| pytest-dev__pytest-7982 |  | yes | existing | yes | N/A | N/A | N/A | N/A | N/A | duplicate | none |
| pytest-dev__pytest-8399 |  | yes | existing | yes | N/A | N/A | N/A | N/A | N/A | duplicate | none |
| scikit-learn__scikit-learn-13496 |  | yes | existing | yes | N/A | N/A | N/A | N/A | N/A | duplicate | none |
| scikit-learn__scikit-learn-26323 |  | yes | existing | yes | N/A | N/A | N/A | N/A | N/A | duplicate | none |
| sphinx-doc__sphinx-8269 |  | yes | existing | yes | N/A | N/A | N/A | N/A | N/A | duplicate | none |
| sphinx-doc__sphinx-8638 |  | yes | existing | yes | N/A | N/A | N/A | N/A | N/A | duplicate | none |
| sympy__sympy-13878 |  | yes | existing | yes | N/A | N/A | N/A | N/A | N/A | duplicate | none |
| sympy__sympy-22914 |  | yes | existing | yes | N/A | N/A | N/A | N/A | N/A | duplicate | none |
| sympy__sympy-23262 |  | yes | existing | yes | N/A | N/A | N/A | N/A | N/A | duplicate | none |
| sympy__sympy-23413 |  | yes | existing | yes | N/A | N/A | N/A | N/A | N/A | duplicate | none |

---

## Best New Candidates

Ranked by verification status and Windows compatibility score:

| Rank | Task ID | Repo | Score | Rationale |
|---|---|---|---|---|
| 1 | `pylint-dev__pylint-6386` | `pylint-dev/pylint` | 9/10 | Verified: baseline fails in 2.89s, single target test, preferred repo |
| 2 | `pylint-dev__pylint-8898` | `pylint-dev/pylint` | 9/10 | Verified: baseline fails in 2.41s, single target test, preferred repo |
| 3 | `psf__requests-5414` | `psf/requests` | 8/10 | Verified: baseline fails in 2.0s, single target test, preferred repo |
| 4 | `psf__requests-6028` | `psf/requests` | 7/10 | Verified: baseline fails in 1.27s, single target test, preferred repo |
| 5 | `pylint-dev__pylint-7080` | `pylint-dev/pylint` | 9/10 | Static score 9/10, 1 fail-to-pass test(s), has test patch, preferred repo, no blockers |
| 6 | `sphinx-doc__sphinx-10323` | `sphinx-doc/sphinx` | 9/10 | Static score 9/10, 1 fail-to-pass test(s), has test patch, preferred repo, no blockers |
| 7 | `sphinx-doc__sphinx-10435` | `sphinx-doc/sphinx` | 9/10 | Static score 9/10, 1 fail-to-pass test(s), has test patch, preferred repo, no blockers |
| 8 | `sphinx-doc__sphinx-10449` | `sphinx-doc/sphinx` | 9/10 | Static score 9/10, 1 fail-to-pass test(s), has test patch, preferred repo, no blockers |

---

## Phase 2 Static Screening: Top 30 Promising Candidates (No Docker, Score ≥ 7)

| Rank | Task ID | Repository | Score | FTP Count | Flags |
|---|---|---|---|---|---|
| 1 | `pylint-dev__pylint-4661` | `pylint-dev/pylint` | 9/10 | 1 | preferred_repo, has_test_patch, single_target_test |
| 2 | `pylint-dev__pylint-6386` | `pylint-dev/pylint` | 9/10 | 1 | preferred_repo, has_test_patch, single_target_test |
| 3 | `pylint-dev__pylint-7080` | `pylint-dev/pylint` | 9/10 | 1 | preferred_repo, has_test_patch, single_target_test |
| 4 | `pylint-dev__pylint-7277` | `pylint-dev/pylint` | 9/10 | 1 | preferred_repo, has_test_patch, single_target_test |
| 5 | `pylint-dev__pylint-8898` | `pylint-dev/pylint` | 9/10 | 1 | preferred_repo, has_test_patch, single_target_test |
| 6 | `sphinx-doc__sphinx-10323` | `sphinx-doc/sphinx` | 9/10 | 1 | preferred_repo, has_test_patch, single_target_test |
| 7 | `sphinx-doc__sphinx-10435` | `sphinx-doc/sphinx` | 9/10 | 1 | preferred_repo, has_test_patch, single_target_test |
| 8 | `sphinx-doc__sphinx-10449` | `sphinx-doc/sphinx` | 9/10 | 1 | preferred_repo, has_test_patch, single_target_test |
| 9 | `sphinx-doc__sphinx-10466` | `sphinx-doc/sphinx` | 9/10 | 1 | preferred_repo, has_test_patch, single_target_test |
| 10 | `sphinx-doc__sphinx-10673` | `sphinx-doc/sphinx` | 9/10 | 1 | preferred_repo, has_test_patch, single_target_test |
| 11 | `sphinx-doc__sphinx-7454` | `sphinx-doc/sphinx` | 9/10 | 1 | preferred_repo, has_test_patch, single_target_test |
| 12 | `sphinx-doc__sphinx-7590` | `sphinx-doc/sphinx` | 9/10 | 1 | preferred_repo, has_test_patch, single_target_test |
| 13 | `sphinx-doc__sphinx-7757` | `sphinx-doc/sphinx` | 9/10 | 1 | preferred_repo, has_test_patch, single_target_test |
| 14 | `sphinx-doc__sphinx-7889` | `sphinx-doc/sphinx` | 9/10 | 1 | preferred_repo, has_test_patch, single_target_test |
| 15 | `sphinx-doc__sphinx-7910` | `sphinx-doc/sphinx` | 9/10 | 1 | preferred_repo, has_test_patch, single_target_test |
| 16 | `sphinx-doc__sphinx-8035` | `sphinx-doc/sphinx` | 9/10 | 1 | preferred_repo, has_test_patch, single_target_test |
| 17 | `sphinx-doc__sphinx-8056` | `sphinx-doc/sphinx` | 9/10 | 1 | preferred_repo, has_test_patch, single_target_test |
| 18 | `sphinx-doc__sphinx-8120` | `sphinx-doc/sphinx` | 9/10 | 1 | preferred_repo, has_test_patch, single_target_test |
| 19 | `sphinx-doc__sphinx-8459` | `sphinx-doc/sphinx` | 9/10 | 1 | preferred_repo, has_test_patch, single_target_test |
| 20 | `sphinx-doc__sphinx-8548` | `sphinx-doc/sphinx` | 9/10 | 1 | preferred_repo, has_test_patch, single_target_test |
| 21 | `sphinx-doc__sphinx-8551` | `sphinx-doc/sphinx` | 9/10 | 1 | preferred_repo, has_test_patch, single_target_test |
| 22 | `sphinx-doc__sphinx-8595` | `sphinx-doc/sphinx` | 9/10 | 1 | preferred_repo, has_test_patch, single_target_test |
| 23 | `sphinx-doc__sphinx-8721` | `sphinx-doc/sphinx` | 9/10 | 1 | preferred_repo, has_test_patch, single_target_test |
| 24 | `sphinx-doc__sphinx-9229` | `sphinx-doc/sphinx` | 9/10 | 1 | preferred_repo, has_test_patch, single_target_test |
| 25 | `sphinx-doc__sphinx-9230` | `sphinx-doc/sphinx` | 9/10 | 1 | preferred_repo, has_test_patch, single_target_test |
| 26 | `sphinx-doc__sphinx-9258` | `sphinx-doc/sphinx` | 9/10 | 1 | preferred_repo, has_test_patch, single_target_test |
| 27 | `sphinx-doc__sphinx-9281` | `sphinx-doc/sphinx` | 9/10 | 1 | preferred_repo, has_test_patch, single_target_test |
| 28 | `sphinx-doc__sphinx-9320` | `sphinx-doc/sphinx` | 9/10 | 1 | preferred_repo, has_test_patch, single_target_test |
| 29 | `sphinx-doc__sphinx-9367` | `sphinx-doc/sphinx` | 9/10 | 1 | preferred_repo, has_test_patch, single_target_test |
| 30 | `sphinx-doc__sphinx-9591` | `sphinx-doc/sphinx` | 9/10 | 1 | preferred_repo, has_test_patch, single_target_test |

---

## Methodology & Safeguards

### Agent/Evaluator Separation

The gold reference solution (column `patch`) was loaded in evaluator context only:
- Never printed or logged in any output file
- Never used to filter, rank, or select candidates
- Never used to judge repair correctness
- Candidates were selected **only** using: `instance_id`, `repo`, `base_commit`, `FAIL_TO_PASS`, `PASS_TO_PASS`, `test_patch`, `problem_statement`, `version`, `difficulty`

### Static Scoring Criteria (Phase 2)

| Factor | Weight | Rationale |
|---|---|---|
| Preferred repo (pylint, sympy, requests, seaborn, flask, sphinx) | +2 | Already verified working on Windows |
| Problematic repo (matplotlib, scikit-learn, astropy) | −3 | C extensions, build complexity |
| Has test patch | +1, missing −2 | Required for deterministic test execution |
| Single fail-to-pass test | +2 | Easiest to verify and reason about |
| External service (redis, postgres, etc.) | −3 | Unavailable in this environment |
| Linux-only API (`/proc/`, `os.fork`) | −2 | Not available on Windows |

### Verification Protocol (Phase 3)

1. Create isolated `tempfile.gettempdir()/ddiv_phase3_verify/<task_id>` workspace
2. `git clone <repo_url>` — fresh clone, no cached state
3. `git checkout <base_commit>` — confirmed by return code 0
4. `python -m venv venv` — isolated Python 3.11 environment
5. `git apply test_patch` — makes target test files exist at their pre-fix state
6. `pip install -e .[testutils/test]` — package in development mode
7. `python -m pytest --collect-only <fail_to_pass_tests>` — test collection check
8. `python -m pytest -v --tb=short -x <fail_to_pass_tests>` — baseline run
9. **Verified eligible:** `pytest` exits with nonzero and `FAILED` in output (defect confirmed)
10. **Ineligible:** `pytest` exits 0 and `PASSED` in output (not useful)
11. Clean up workspace; preserve logs in `verification_logs/<task_id>/`

---

## Remaining Blockers and Next Steps

### Priority 1 — Immediate Verification (Phase 3 completion)

The following tasks have the highest static scores and should be the first priority for Phase 3 verification:

- `pylint-dev__pylint-4661` — v2.10, single test `test_pylint_home`
- `pylint-dev__pylint-6386` — v2.14, single test `test_short_verbose`
- `pylint-dev__pylint-7080` — v2.15, single test `test_ignore_path_recursive_current_dir`
- `pylint-dev__pylint-7277` — v2.15, single test `test_modify_sys_path`
- `pylint-dev__pylint-8898` — v3.0, single test `test_csv_regex_error`
- `psf__requests-5414` — v2.26, single test URL validation
- `psf__requests-6028` — v2.27, single test `test_prepend_scheme_if_needed`
- `sphinx-doc__sphinx-10323` — v5.0, single test `test_LiteralIncludeReader_...`

### Known Blockers by Category

| Blocker | Affected Tasks | Mitigation |
|---|---|---|
| Docker required | 34 tasks | No mitigation — excluded |
| C extension build | matplotlib (34), scikit-learn (32), astropy (22) | Excluded from Phase 3 |
| No test patch | Some tasks | Excluded from Phase 3 |
| No fail-to-pass tests | Some tasks | Excluded |
| Test passes at baseline | To be determined by Phase 3 | Reclassified to ineligible |

---

*This report was generated by DDIV Candidate Screening v1.0. Screening date: 2026-10-15 15:19 UTC.*
*Phase 3 verification logs: `results/candidate_screening_20261015T144611Z/verification_logs/`*
