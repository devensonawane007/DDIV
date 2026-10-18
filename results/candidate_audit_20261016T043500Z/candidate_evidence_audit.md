# DDIV Candidate Evidence Audit

**Audit Date:** 2026-10-16T04:35:00Z  
**Logs Root:** `D:/DDIV/results/candidate_screening_20261015T144611Z/verification_logs/`  
**Dataset:** `D:/DDIV/data/swebench/test-00000-of-00001.parquet`  
**Gold Patch Confidentiality:** Maintained 100%. No gold patch contents were accessed or inspected.

---

## 1. Audit Framework & Classification Standards

Each empirically evaluated candidate was audited across seven verification criteria:
1. **Provenance & Checkout:** Git clone and checkout to specified `base_commit` confirmed by exit code 0.
2. **Environment Isolation:** Provisioned inside a dedicated virtual environment with explicit runtime versions.
3. **Test Patch Application:** `test_patch` applied cleanly via `git apply --ignore-whitespace` without touching gold patch.
4. **Target Test Collection:** `pytest --collect-only` identifies exactly the tests listed in `FAIL_TO_PASS`.
5. **Defect Reproduction:** Baseline test run fails specifically due to the reported bug assertion, **not** an import error, collection error, or missing dependency.
6. **Execution Timing:** Baseline test runtime measured and confirmed $< 30$ seconds.
7. **Traceability:** Unbroken log trail preserved in `verification_logs/<task_id>/`.

### Classification Definitions
- `VERIFIED_ELIGIBLE`: All 7 criteria satisfied; intended defect confirmed by test failure.
- `NEEDS_RECHECK`: Evidence is promising but ambiguous, or behavior on host OS requires further controlled testing.
- `BLOCKED`: A deterministic dependency or environment incompatibility prevents execution.
- `REJECTED`: Test passes at baseline (no defect) or is unfixable under test protocol.
- `STATIC_PROMISING`: Static metadata matches, but empirical verification has not yet occurred.

---

## 2. In-Depth Audit of the Four Verified Candidates

### 2.1 Candidate: `pylint-dev__pylint-6386`
- **Repository:** `pylint-dev/pylint`
- **Target Software Version:** `2.14`
- **Base Commit:** `754b487f4d892e3d4872b6fc7468a71db4e31c13`
- **FAIL_TO_PASS Test:** `tests/config/test_config.py::test_short_verbose`
- **Audit Verdict:** `VERIFIED_ELIGIBLE`

#### Evidence Checklist & Log Traceability
- **Checkout Log:** `verification_logs/pylint-dev__pylint-6386/checkout.log`
  ```text
  RC: 0
  STDOUT: Note: switching to '754b487f4d892e3d4872b6fc7468a71db4e31c13'.
  HEAD is now at 754b487f4 Fix crash with empty type annotation (#6385)
  ```
- **Patch Application Log:** `verification_logs/pylint-dev__pylint-6386/patch_apply.log`
  ```text
  RC: 0
  ```
- **Collection Log:** `verification_logs/pylint-dev__pylint-6386/collect.log`
  ```text
  RC: 0
  STDOUT: tests/config/test_config.py::test_short_verbose
  1 test collected in 1.06s
  ```
- **Baseline Execution Log:** `verification_logs/pylint-dev__pylint-6386/baseline_run.log`
  ```text
  RC: 1
  STDOUT:
  ============================= test session starts =============================
  collecting ... collected 1 item
  tests/config/test_config.py::test_short_verbose FAILED                   [100%]
  ================================== FAILURES ===================================
  E   argparse.ArgumentError: argument --verbose/-v: expected one argument
  ...
  E   SystemExit: 2
  ---------------------------- Captured stderr call -----------------------------
  usage: pylint [options]
  pylint: error: argument --verbose/-v: expected one argument
  =========================== short test summary info ===========================
  FAILED tests/config/test_config.py::test_short_verbose - SystemExit: 2
  ======================= 1 failed, 160 warnings in 1.06s =======================
  ```
- **Defect Fidelity Confirmation:**
  The problem statement specifically reports: *"The short option of the `verbose` option expects an argument... `pylint mytest.py -v` results in `pylint: error: argument --verbose/-v: expected one argument`"*. The baseline test failure reproduces this exact `argparse.ArgumentError` and `SystemExit: 2`. This is a 100% fidelity reproduction of the reported issue.
- **Runtime:** 2.89s total harness time (1.06s pytest test session).

---

### 2.2 Candidate: `pylint-dev__pylint-8898`
- **Repository:** `pylint-dev/pylint`
- **Target Software Version:** `3.0`
- **Base Commit:** `1f8c4d9eb185c16a2c1d881c054f015e1c2eb334`
- **FAIL_TO_PASS Test:** `tests/config/test_config.py::test_csv_regex_error`
- **Audit Verdict:** `VERIFIED_ELIGIBLE`

#### Evidence Checklist & Log Traceability
- **Checkout Log:** `verification_logs/pylint-dev__pylint-8898/checkout.log`
  ```text
  RC: 0
  HEAD is now at 1f8c4d9eb Improve docstring in bad-names-rgxs and other related regex options (#8897)
  ```
- **Patch Application Log:** `verification_logs/pylint-dev__pylint-8898/patch_apply.log`
  ```text
  RC: 0
  ```
- **Collection Log:** `verification_logs/pylint-dev__pylint-8898/collect.log`
  ```text
  RC: 0
  STDOUT: tests/config/test_config.py::test_csv_regex_error
  1 test collected in 1.07s
  ```
- **Baseline Execution Log:** `verification_logs/pylint-dev__pylint-8898/baseline_run.log`
  ```text
  RC: 1
  STDOUT:
  ============================= test session starts =============================
  collecting ... collected 1 item
  tests/config/test_config.py::test_csv_regex_error FAILED                 [100%]
  ================================== FAILURES ===================================
  tests\config\test_config.py:171: in test_csv_regex_error
      assert (
  E   AssertionError: assert 'Error in provided regular expression: (foo{1,} beginning at index 0: missing ), unterminated subpattern' in 'usage: pylint [options]\npylint: error: argument --bad-names-rgxs: Error in provided regular expression: (foo{1 beginning at index 0: missing ), unterminated subpattern\n'
  =========================== short test summary info ===========================
  FAILED tests/config/test_config.py::test_csv_regex_error - AssertionError
  ============================== 1 failed in 0.59s ==============================
  ```
- **Defect Fidelity Confirmation:**
  The problem statement states: *"Since pylint splits on commas in this option, instead of taking a list of strings, if there are any commas in the regular expression, the result is mangled before being parsed."* The test asserts that the regex `(foo{1,}` should be parsed intact, but pylint split it at the comma into `(foo{1`. The test failed precisely on this assertion. Complete defect fidelity.
- **Runtime:** 2.41s total harness time (0.59s pytest test session).

---

### 2.3 Candidate: `psf__requests-5414`
- **Repository:** `psf/requests`
- **Target Software Version:** `2.26`
- **Base Commit:** `39d0fdd9096f867bc5828dbd6c6e75a9b9a52865`
- **FAIL_TO_PASS Test:** `tests/test_requests.py::TestRequests::test_invalid_url[InvalidURL-http://.example.com]`
- **Audit Verdict:** `VERIFIED_ELIGIBLE`

#### Evidence Checklist & Log Traceability
- **Checkout Log:** `verification_logs/psf__requests-5414/checkout.log`
  ```text
  RC: 0
  HEAD is now at 39d0fdd9 Update tests to use valid httpbin cert (#5409)
  ```
- **Patch Application Log:** `verification_logs/psf__requests-5414/patch_apply.log`
  ```text
  RC: 0
  ```
- **Collection Log:** `verification_logs/psf__requests-5414/collect.log`
  ```text
  RC: 0
  STDOUT: tests/test_requests.py::TestRequests::test_invalid_url[InvalidURL-http://.example.com]
  1 test collected in 0.47s
  ```
- **Baseline Execution Log:** `verification_logs/psf__requests-5414/baseline_run.log`
  ```text
  RC: 1
  STDOUT:
  ============================= test session starts =============================
  collecting ... collected 1 item
  tests/test_requests.py::TestRequests::test_invalid_url[InvalidURL-http://.example.com] FAILED [100%]
  ================================== FAILURES ===================================
  E   urllib3.exceptions.LocationParseError: Failed to parse: '.example.com', label empty or too long
  =========================== short test summary info ===========================
  FAILED tests/test_requests.py::TestRequests::test_invalid_url[InvalidURL-http://.example.com]
  ============================== 1 failed in 0.56s ==============================
  ```
- **Defect Fidelity Confirmation:**
  The problem statement states: *"Attempting to get e.g. `http://.example.com` results in a `UnicodeError` [or underlying urllib3 parse error]. It seems like the intention so far has been to raise `InvalidURL` instead"*. The test checks `with pytest.raises(InvalidURL): requests.get(url)`. On the unpatched base, `LocationParseError` escaped uncaught, causing the test to fail. Complete defect fidelity.
- **Runtime:** 2.00s total harness time (0.56s pytest test session).

---

### 2.4 Candidate: `psf__requests-6028`
- **Repository:** `psf/requests`
- **Target Software Version:** `2.27`
- **Base Commit:** `0192aac2412389657053be416208579434e38e58`
- **FAIL_TO_PASS Tests:**
  1. `tests/test_utils.py::test_prepend_scheme_if_needed[http://user:pass@example.com/path?query-http://user:pass@example.com/path?query]`
  2. `tests/test_utils.py::test_prepend_scheme_if_needed[http://user@example.com/path?query-http://user@example.com/path?query]`
- **Audit Verdict:** `VERIFIED_ELIGIBLE`

#### Evidence Checklist & Log Traceability
- **Checkout Log:** `verification_logs/psf__requests-6028/checkout.log`
  ```text
  RC: 0
  HEAD is now at 0192aac2 Add certifi requirement to setup.py (#5998)
  ```
- **Patch Application Log:** `verification_logs/psf__requests-6028/patch_apply.log`
  ```text
  RC: 0
  ```
- **Collection Log:** `verification_logs/psf__requests-6028/collect.log`
  ```text
  RC: 0
  STDOUT:
  tests/test_utils.py::test_prepend_scheme_if_needed[http://user:pass@example.com/path?query-http://user:pass@example.com/path?query]
  tests/test_utils.py::test_prepend_scheme_if_needed[http://user@example.com/path?query-http://user@example.com/path?query]
  2 tests collected in 0.35s
  ```
- **Baseline Execution Log:** `verification_logs/psf__requests-6028/baseline_run.log`
  ```text
  RC: 1
  STDOUT:
  ============================= test session starts =============================
  collecting ... collected 2 items
  tests/test_utils.py::test_prepend_scheme_if_needed[http://user:pass@example.com/path?query-http://user:pass@example.com/path?query] FAILED [ 50%]
  tests/test_utils.py::test_prepend_scheme_if_needed[http://user@example.com/path?query-http://user@example.com/path?query] FAILED [100%]
  ================================== FAILURES ===================================
  E   AssertionError: assert 'http://examp...om/path?query' == 'http://user:...om/path?query'
  E     - http://user:pass@example.com/path?query
  E     + http://example.com/path?query
  ...
  E   AssertionError: assert 'http://examp...om/path?query' == 'http://user@...om/path?query'
  E     - http://user@example.com/path?query
  E     + http://example.com/path?query
  =========================== short test summary info ===========================
  FAILED tests/test_utils.py::test_prepend_scheme_if_needed[http://user:pass@example.com/path?query-http://user:pass@example.com/path?query]
  FAILED tests/test_utils.py::test_prepend_scheme_if_needed[http://user@example.com/path?query-http://user@example.com/path?query]
  ============================== 2 failed in 0.33s ==============================
  ```
- **Defect Fidelity Confirmation:**
  The problem statement reports proxy authentication failures caused by authentication credentials being stripped from URLs during normalization. The test specifically checks that `prepend_scheme_if_needed` preserves `user:pass@` in URLs. On the unpatched base, it stripped them to `http://example.com/...`. The test caught this exact assertion failure in both parametrized cases. Complete defect fidelity.
- **Runtime:** 1.27s total harness time (0.33s pytest test session).

---

## 3. Audit of the Five Additional Checked Tasks

### 3.1 `sphinx-doc__sphinx-10323`
- **Audit Verdict:** `NEEDS_RECHECK`
- **Target Test:** `tests/test_directive_code.py::test_LiteralIncludeReader_dedent_and_append_and_prepend`
- **Baseline Result:** RC 0, `1 xfailed in 0.52s`.
- **Root Cause Analysis:**
  Inspection of `test_patch` revealed that the author decorated the test with:
  ```python
  @pytest.mark.xfail(os.name != 'posix', reason="Not working on windows")
  def test_LiteralIncludeReader_dedent_and_append_and_prepend(literal_inc_path):
  ```
  On Windows (`os.name == 'nt'`), pytest treats the test as expected-to-fail (`XFAIL`), exiting with return code 0. Because SWE-bench verification relies on an explicit failure-to-pass transition, on native Windows this test produces no failure status without pytest arguments like `--runxfail`. Additionally, if the test fails on Windows due to carriage returns (`\r\n`), it may remain failing even after the bug is fixed.
- **Recheck Action Required:** Test execution under Linux/Docker container or with `--runxfail` to determine whether Windows line-ending differences cause an unfixable failure.

### 3.2 `pylint-dev__pylint-4661` & `pylint-dev__pylint-4604`
- **Audit Verdict:** `BLOCKED` (Python 3.11 Standard Library Incompatibility)
- **Baseline Result:** RC 4, `ImportError while loading conftest`.
- **Root Cause Analysis:**
  Log excerpt from `verification_logs/pylint-dev__pylint-4661/collect.log`:
  ```text
  from wrapt.decorators import ismethod, isclass, formatargspec
  ImportError: cannot import name 'formatargspec' from 'inspect'
  ```
  `inspect.formatargspec` was deprecated in Python 3.5 and completely removed in Python 3.11. Older pylint releases ($\le 2.10$) pinned older `astroid` and `wrapt` releases that import `formatargspec`. These tasks cannot run on Python 3.11 without Docker or an isolated Python $\le 3.10$ interpreter.

### 3.3 `pylint-dev__pylint-7277`
- **Audit Verdict:** `BLOCKED` (Legacy Pytest/Py Dependency Mismatch)
- **Baseline Result:** RC 4, `ERROR collecting tests/test_self.py`.
- **Root Cause Analysis:**
  Log excerpt from `verification_logs/pylint-dev__pylint-7277/baseline_run.log`:
  ```text
  from py._path.local import LocalPath
  ModuleNotFoundError: No module named 'py._path'; 'py' is not a package
  ```
  Pylint 2.15's test suite at this commit imported `py._path.local.LocalPath` directly. Modern pytest releases (pytest 7.2+) decoupled from the legacy `py` library, causing this test import to fail.

### 3.4 `sphinx-doc__sphinx-8721`
- **Audit Verdict:** `BLOCKED` (Unpinned Jinja2 API Deprecation)
- **Baseline Result:** RC 1, `ImportError while importing plugin "sphinx.testing.fixtures"`.
- **Root Cause Analysis:**
  Log excerpt from `verification_logs/sphinx-doc__sphinx-8721/baseline_run.log`:
  ```text
  from jinja2 import Environment, environmentfilter
  ImportError: cannot import name 'environmentfilter' from 'jinja2'
  ```
  Jinja2 3.1.0 removed `environmentfilter` (replaced by `pass_environment`). In unpinned installations, pip resolved modern Jinja2 (3.1.6), breaking Sphinx 3.5's test fixture plugins.
