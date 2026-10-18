# DDIV v2.2 Recovery Effectiveness Audit

**Audit Target:** Multi-Agent Recovery Mechanics Across 5 `FULL_DDIV` Pilot Runs  
**Audit Date:** 2026-10-14  
**Audit Directory:** `results/v2_2_development/pilot_audit_20261014_1850/`

---

## 1. Audit Framework: Four-Stage Recovery Validation

To prevent claiming recovery improvement merely because recovery code executed, this audit evaluates each run across four distinct stages:
1. **Stage 1: Invocation:** Was the recovery component (`V22SupervisedWorker`, `ProposalHistory`, `FailureDisambiguator`, Supervisor) invoked?
2. **Stage 2: Delivery:** Did structured feedback (negative constraints, disambiguated failure modes) reach the subsequent Coder prompt?
3. **Stage 3: Behavioral Change:** Did the subsequent Coder proposal change its target, operation, or anchor to avoid the prior error?
4. **Stage 4: Outcome Improvement:** Did the change result in an improved evaluation outcome (compilation, patch application, F2P pass, or resolution)?

---

## 2. Per-Task Recovery Audit Evidence

### 2.1 `pylint-dev__pylint-6903` (FULL_DDIV: 3 Attempts)
- **Attempt 1:**
  - Coder proposed modifying phantom path `path/to/your/file.py` at anchor `if cpu_quota and cpu_quota != -1...`.
  - Failure: `PATCH_BUILDER_FAILED: Target file not found in workspace`.
- **Stage 1 (Invocation):** `V22SupervisedWorker` recorded proposal in `ProposalHistory`. Supervisor diagnosed `F3` (file path error).
- **Stage 2 (Delivery):** Supervisor delivered directive: `"Regenerate the patch targeting the correct file: 'pylint/lint/run.py'"` with negative constraint: `"CRITICAL DIRECTIVE: DO NOT REPEAT PREVIOUS FAILED PROPOSALS: - Attempt 1: Modified 'path/to/your/file.py'"`.
- **Stage 3 (Behavioral Change):** **YES.** In Attempt 2, Coder corrected target file to `pylint/lint/run.py` at anchor `return cpu_quota and cpu_quota != -1...`.
- **Stage 4 (Outcome Improvement):** **PARTIAL.** Patch was successfully built by `DemoPatchBuilder`, but `git apply` failed due to line context drift. Attempt 3 diff missed hunk headers. Resolved: **False**.

### 2.2 `mwaskom__seaborn-3187` (FULL_DDIV: 3 Attempts)
- **Attempt 1:**
  - Coder proposed two `insert_after` modifications targeting anchors `class CatScale` and `def tick(self, loc`.
  - Failure: Neither anchor existed in `seaborn/_core/scales.py`.
- **Stage 1 (Invocation):** Supervisor diagnosed `F3` (syntax/anchor mismatch).
- **Stage 2 (Delivery):** Supervisor instructed targeting `Continuous.get_legend_info` to retrieve offset from `ScalarFormatter`. Negative constraints delivered.
- **Stage 3 (Behavioral Change):** **YES.** In Attempt 2, Coder changed target anchor to `def get_legend_info(self, formatter):`.
- **Stage 4 (Outcome Improvement):** **NO.** The exact signature `def get_legend_info(self, formatter):` was also absent from the file. Coder fell back to raw diff which lacked hunk headers (`missing ---, +++, or @@`). Attempt 3 repeated the missing anchor. Resolved: **False**.

### 2.3 `pydata__xarray-7393` (FULL_DDIV: 3 Attempts)
- **Attempt 1:**
  - Coder proposed `insert_before` at anchor `def concat(`.
  - Failure: `DemoPatchBuilder` flagged ambiguous anchor (3 matches in `xarray/core/indexes.py`).
- **Stage 1 (Invocation):** Supervisor diagnosed ambiguous anchor context.
- **Stage 2 (Delivery):** Supervisor warned: `"Do NOT use ambiguous anchors... Ensure anchor is unique"`.
- **Attempt 2:** Coder repeated `def concat(` with `replace` operation. Supervisor repeated warning.
- **Stage 3 (Behavioral Change):** **YES (in Attempt 3).** In Attempt 3, Coder shifted away from `def concat(` and targeted `def _asarray_tuplesafe`.
- **Stage 4 (Outcome Improvement):** **PARTIAL.** Patch built cleanly and passed AST validation. However, `git apply` failed at target location. Resolved: **False**.

### 2.4 `astropy__astropy-8872` (FULL_DDIV: 3 Attempts)
- **Attempt 1:**
  - Coder targeted test file `astropy/time/tests/test_quantity_interaction.py` at anchor `q = 2450000.125*u.day`.
  - Outcome: Patch applied to test file, but FAIL_TO_PASS test `test_preserve_dtype` failed.
- **Stage 1 (Invocation):** Supervisor diagnosed regression/irrelevant test patch.
- **Stage 2 (Delivery):** Supervisor instructed Coder to target source code `astropy/units/quantity.py` for float16 handling.
- **Stage 3 (Behavioral Change):** **YES.** In Attempt 2, Coder moved from test file to `astropy/units/quantity.py`.
- **Stage 4 (Outcome Improvement):** **NO.** In Attempts 2 & 3, Coder used a hallucinated function signature anchor `def __new__(cls, value, unit=None, dtype=None, copy=True, subok=True, ndmin=0, **kwargs):` which was not found in the source file. Resolved: **False**.

### 2.5 `psf__requests-2931` (FULL_DDIV: 3 Attempts)
- **Attempt 1:**
  - Coder proposed modifying `requests/utils.py` at anchor `def to_native_string(string, encoding='ascii'):`.
  - Failure: Anchor not found.
- **Stage 1 & 2:** Supervisor warned that anchor did not match current source.
- **Stage 3 (Behavioral Change):** **NO.** In Attempt 2 and Attempt 3, Coder repeatedly generated the identical stale anchor string despite explicit supervisor directives.
- **Stage 4 (Outcome Improvement):** **NO.** Patch never applied. Resolved: **False**.

---

## 3. Summary of Recovery Effectiveness

| Task ID | Stage 1: Invoked | Stage 2: Delivered | Stage 3: Behavior Changed | Stage 4: Outcome Improved | Primary Reason Outcome Failed |
| :--- | :---: | :---: | :---: | :---: | :--- |
| `pylint-6903` | ✅ YES | ✅ YES | ✅ YES (fixed path) | ⚠️ Partial (patch built, apply failed) | Context line drift in diff hunk |
| `seaborn-3187` | ✅ YES | ✅ YES | ✅ YES (changed method) | ❌ NO | Hallucinated method signature anchor |
| `xarray-7393` | ✅ YES | ✅ YES | ✅ YES (shifted anchor) | ⚠️ Partial (patch built, apply failed) | C-extension dependencies & git apply drift |
| `astropy-8872` | ✅ YES | ✅ YES | ✅ YES (test -> source) | ❌ NO | Hallucinated function signature anchor |
| `requests-2931` | ✅ YES | ✅ YES | ❌ NO (anchor repeated) | ❌ NO | 7B model anchor fixation on hallucinated signature |

### 4. Empirical Conclusion on Recovery Dynamics
1. **Mechanical Integrity:** The v2.2 recovery plumbing (`V22SupervisedWorker`, `ProposalHistory`, negative constraint injection) functioned with 100% reliability. Feedback was accurately constructed, formatted, and received by the Coder across all attempts.
2. **Model Capacity Bottleneck:** The local `qwen2.5-coder:7b` model frequently exhibited "anchor hallucination"—generating function signatures from its pre-training weights rather than extracting the exact string from the repository file. Because `DemoPatchBuilder` enforces exact string matching, anchor mismatches prevented patches from building or applying.
3. **No Direct Repair Yield:** While recovery changed proposal behavior in 3 of 5 tasks, it did not overcome the 7B model's anchor hallucination barrier, resulting in 0/5 resolved tasks under `FULL_DDIV`.
