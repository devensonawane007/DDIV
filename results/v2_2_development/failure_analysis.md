# DDIV v2.2 Root-Cause Failure Analysis

**Evaluation Context:** Controlled 3-Task Local Ollama Pilot (qwen2.5-coder:7b)  
**Tasks:** pylint-dev__pylint-6903, pylint-dev__pylint-4970, sympy__sympy-23413  
**Conditions:** BASELINE (1 attempt), RETRY_ONLY (up to 3 blind attempts), FULL_DDIV (up to 3 supervisor/RCA-guided attempts)  
**Total Runs:** 9 completed runs | **Total Attempts:** 20 executed attempts  
**Status:** Audit & Analysis Complete  

---

## 1. Executive Summary & Verification of Denominators

The 9 planned runs in 
esults/local_ollama_coder/results/ were audited against comparison_summary.json and local_ollama_comparison.csv. All 9 runs completed cleanly with zero provider timeouts, zero unhandled exceptions, and zero silent cloud fallbacks.

- **BASELINE (3 runs, 3 attempts):** 0 resolved (0.0%), 0 Pass@1. Avg Tokens: 8,857.0.
- **RETRY_ONLY (3 runs, 9 attempts):** 0 resolved (0.0%), 0 Pass@1. Avg Tokens: 26,537.3.
- **FULL_DDIV (3 runs, 8 attempts):** 1 resolved (33.3%), 0 Pass@1. Avg Tokens: 35,104.0.

`
Total Attempts Breakdown (N=20):
├── RESOLVED: 1 attempt (5.0%)  [pylint-6903 full_ddiv attempt 2]
├── INCORRECT_REPAIR_LOGIC: 7 attempts (35.0%)
├── INVALID_PATCH_CONSTRUCTION: 5 attempts (25.0%)
├── INADEQUATE_CODE_LOCATION: 4 attempts (20.0%)
├── MODEL_PLACEHOLDER_HALLUCINATION: 3 attempts (15.0%)
└── REPEATED_PATCH_CYCLE: 2 attempts (10.0% of failures, overlaps blind retry)
`

---

## 2. Taxonomy of Empirical Failure Modes

### Category A: Model Placeholder Hallucination (path/to/...)
- **Observed In:** pylint-dev__pylint-4970 (Full_DDIV Attempt 1, Retry_Only Attempts 2 & 3).
- **Evidence:** Coder outputs path/to/file.py and path/to/similar_checker.py.
- **Mechanism:** The 7B model defaults to prompt example patterns when uncertain about repository path structures.
- **Underlying Cause:** Lack of strict prompt gating forcing the Coder to select solely from the verified file list provided by Locator.

### Category B: Indentation & Block Scope Corruption (INVALID_PATCH_CONSTRUCTION)
- **Observed In:** 
  - pylint-dev__pylint-4970 (Baseline Attempt 1, Retry_Only Attempt 1, Full_DDIV Attempt 2).
  - pylint-dev__pylint-6903 (Retry_Only Attempts 2 & 3).
- **Evidence:** 
  - insert_before on def process_module(self, node): placed code at class level above the method, breaking 10/10 regression tests.
  - insert_after on vail_cpu = int(...) produced unexpected indent (<unknown>, line 57).
  - Full_DDIV Attempt 3 produced raw diff missing standard @@ -start,len +start,len @@ hunk headers.
- **Underlying Cause:** DemoPatchBuilder lacks block-aware indentation normalization for insertion operations.

### Category C: Code Localization Deficit (INADEQUATE_CODE_LOCATION)
- **Observed In:** sympy__sympy-23413 (Full_DDIV Attempts 1, 2, 3).
- **Evidence:**
  - Locator identified: ['sympy/matrices/matrices.py', 'sympy/matrices/matrixbase.py', 'sympy/matrices/dense.py'].
  - True definition: sympy/matrices/normalforms.py (line 70) and sympy/polys/matrices/normalforms.py (line 339).
  - Coder attempted anchors in matrices.py (def hermite_normal_form(...)), which did not exist, triggering repeated Anchor not found.
- **Underlying Cause:** Locator search missed 
ormalforms.py. Supervisor reinforced this deficit by instructing Coder to stick exclusively to the files identified by Locator.

### Category D: Incomplete Repair Logic (INCORRECT_REPAIR_LOGIC)
- **Observed In:** pylint-dev__pylint-6903 (Baseline Attempt 1, Retry_Only Attempt 1), sympy__sympy-23413 (Baseline Attempt 1, Retry_Only Attempts 1 & 2).
- **Evidence:**
  - In pylint-6903, Coder only protected cpu_quota / cpu_period with max(..., 1) but left cpu_shares / 1024 unprotected.
  - In sympy-23413, Coder attempted _iszero(x): return x.is_zero and not x.is_zero (tautological False).
- **Underlying Cause:** Partial fix syndrome and algorithmic reasoning limits in the 7B model.

### Category E: Blind Repetition Cycles (REPEATED_PATCH_CYCLE)
- **Observed In:** All three tasks under RETRY_ONLY.
- **Evidence:** In RETRY_ONLY, Attempt 3 repeated Attempt 2 byte-for-byte in all cases (path/to/similar_checker.py, 
eturn x.is_zero and not x.has(Matrix), unexpected indent).
- **Underlying Cause:** RETRY_ONLY provides zero failure feedback or negative constraints, causing low-temperature sampling to generate identical completions.

---

## 3. Discrepancy Audit: Reported Failure Detector vs. True Root Cause

| Run | Attempt | Reported Category | True Verified Cause | Discrepancy Reason |
| :--- | :---: | :--- | :--- | :--- |
| pylint-4970__baseline | 1 | PATCH_INVALID | INVALID_PATCH_CONSTRUCTION | Code applied at class body level; AST valid, but broke 10 regression tests. |
| pylint-4970__full_ddiv | 1 | ANCHOR_NOT_FOUND | MODEL_PLACEHOLDER_HALLUCINATION | File was path/to/file.py. Root cause is hallucinated path, not missing anchor. |
| pylint-4970__full_ddiv | 2 | ANCHOR_NOT_FOUND | INVALID_PATCH_CONSTRUCTION | Anchor was found; error was AST syntax error invalid syntax line 819. |
| pylint-6903__retry_only| 2 | ANCHOR_NOT_FOUND | INVALID_PATCH_CONSTRUCTION | Anchor was found; error was AST syntax error unexpected indent line 57. |
| sympy-23413__full_ddiv | 1 | ANCHOR_NOT_FOUND | INADEQUATE_CODE_LOCATION | Target file sympy/matrices/expressions/matrix.py does not exist. |

> [!IMPORTANT]
> The internal FailureDetectorAgent frequently misclassifies AST syntax errors and missing target files as ANCHOR_NOT_FOUND. Recovery logic relying on GranularFailureType.ANCHOR_NOT_FOUND thus delivers misaligned advice to the Supervisor.

---

## 4. Observed Facts vs. Hypotheses & Recommendations

### Observed Empirical Facts:
1. When Supervisor provides precise file and symbol feedback (as in pylint-6903 Attempt 2), qwen2.5-coder:7b can synthesize correct code (
eturn avail_cpu or 1) and pass all tests.
2. Blind retries without feedback achieve 0% resolution across all 3 tasks and frequently collapse into deterministic repetition cycles.
3. Patch construction failures account for 40% of all failed attempts (placeholder paths + syntax/indentation errors).

### Hypotheses:
1. Automatically constraining Coder prompts to valid, existing file paths will eliminate 100% of path/to/... hallucinations.
2. Block-aware indentation adjustment in DemoPatchBuilder will prevent indentation errors when inserting code inside function bodies.
3. Supplying past failed patch signatures to the Coder prompt will break deterministic repetition loops.

---

## 5. Required Targeted Improvements for DDIV v2.2

1. **Strict Target-Path Validation & Prompt Enforcement**: Validate that target files exist in workspace before patch synthesis; instruct Coder with an explicit enumeration of valid files.
2. **Context-Aware Indentation Normalizer**: Detect anchor indentation level and normalize inserted code lines to preserve enclosing block indentation.
3. **Accurate Granular Failure Disambiguation**: Separate TARGET_FILE_NOT_FOUND, SYNTAX_ERROR_INDENTATION, and ANCHOR_NOT_FOUND in failure detection.
4. **Anti-Repetition Negative Constraints**: Pass previously failed patch proposals into retry and recovery prompts to prevent REPEATED_PATCH_CYCLE.
5. **Supervisor Recovery Grounding**: Ensure Supervisor checks workspace existence before confirming target file advice.
