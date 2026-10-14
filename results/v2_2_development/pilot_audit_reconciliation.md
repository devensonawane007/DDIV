# DDIV Pilot Audit & Evidence Reconciliation Report

**Document Date:** October 13, 2026  
**Audited Artifacts:**
- `results/local_ollama_coder/comparison_summary.json`
- `results/local_ollama_coder/local_ollama_comparison.csv`
- `results/local_ollama_coder/local_ollama_report.md`
- `results/local_ollama_coder/results/` (9 individual run records)
- Historical baseline/demo runs in `results/demo_reproduction/` and `results/fair_comparison_pylint6903/`

---

## 1. Metric Reconciliation: Aggregate vs. Per-Run Records

Every single scalar metric in the rolling summary and CSV was audited against the 9 underlying JSON result files. Zero missing records or checksum inconsistencies were found.

| Task ID | Condition | Status | Resolved | Attempts | Tokens (Rec) | Tokens (Summary) | Duration | Match |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `pylint-dev__pylint-6903` | baseline | COMPLETED | False | 1 | 9,564 | 9,564 | 228.4s | EXACT |
| `pylint-dev__pylint-6903` | retry_only | COMPLETED | False | 3 | 28,152 | 28,152 | 323.0s | EXACT |
| `pylint-dev__pylint-6903` | full_ddiv | COMPLETED | True | 2 | 32,760 | 32,760 | 381.2s | EXACT |
| `pylint-dev__pylint-4970` | baseline | COMPLETED | False | 1 | 9,395 | 9,395 | 131.7s | EXACT |
| `pylint-dev__pylint-4970` | retry_only | COMPLETED | False | 3 | 27,809 | 27,809 | 268.7s | EXACT |
| `pylint-dev__pylint-4970` | full_ddiv | COMPLETED | False | 3 | 38,715 | 38,715 | 243.7s | EXACT |
| `sympy__sympy-23413` | baseline | COMPLETED | False | 1 | 7,612 | 7,612 | 181.4s | EXACT |
| `sympy__sympy-23413` | retry_only | COMPLETED | False | 3 | 23,651 | 23,651 | 374.0s | EXACT |
| `sympy__sympy-23413` | full_ddiv | COMPLETED | False | 3 | 33,837 | 33,837 | 441.7s | EXACT |

---

## 2. Model Provider & Zero-Fallback Verification

Across all 20 attempts recorded in the 9 runs:
- **Coder Invocations:** Exactly 20 Coder model calls.
  - Model: `qwen2.5-coder:7b`
  - Provider: `ollama` (`http://localhost:11434`)
  - Format: non-streaming JSON mode (`format: "json"`)
  - Cloud Fallback Count: **0** (strictly zero fallback to Groq, Gemini, or any cloud API).
- **Supporting Agent Invocations:**
  - Locator: `gemini-3.1-flash-lite` via Gemini API.
  - TestUnderstanding / Tester / PatchCritic / Supervisor: `qwen/qwen3.8-27b` via Groq API.

---

## 3. Separation of Historical Experiments vs. Local Ollama Pilot

To ensure academic and experimental integrity, earlier experiment packages remain strictly isolated:

1. **Demo Reproduction (`results/demo_reproduction/`):**
   - Evaluated single-task demo `pylint-dev__pylint-6903` under cloud Coder (`openai/gpt-oss-120b`).
   - Outcome: FULL_DDIV resolved on Attempt 1 (15,815 tokens).
   - Separation: Stored in independent directory with separate manifest.
2. **Fair Comparison Demo (`results/fair_comparison_pylint6903/`):**
   - Evaluated `pylint-dev__pylint-6903` under Groq cloud Coder across BASELINE, RETRY_ONLY, and FULL_DDIV.
   - Outcome: RETRY_ONLY resolved on Attempt 2 (19,923 tokens); FULL_DDIV resolved on Attempt 1 (15,815 tokens).
   - Separation: Historical record preserved; not mixed into the Ollama numbers.
3. **Local Ollama Pilot (`results/local_ollama_coder/`):**
   - Evaluated 3 distinct tasks (`pylint-6903`, `pylint-4970`, `sympy-23413`) under local `qwen2.5-coder:7b`.
   - Outcome: BASELINE 0/3, RETRY_ONLY 0/3, FULL_DDIV 1/3 (`pylint-6903` on Attempt 2, 32,760 tokens).
   - Separation: Fully self-contained in `results/local_ollama_coder/`.

---

## 4. Audit Findings & Discrepancies Noted

1. **Failure Detector Heuristic Misclassification:**
   - In 5 of the 19 failed attempts, the internal failure detector labeled the error as `GranularFailureType.ANCHOR_NOT_FOUND` when the actual failure was an AST indentation syntax error or a missing file path.
   - This did not affect test verdicts (which are deterministically governed by Tier-1 test runner exit codes), but it polluted the diagnostic feedback given to the Supervisor.
2. **Token Accounting Representation:**
   - In raw `ExperimentConditionRecord` outputs, token metrics are nested under `record.metrics.total_tokens` rather than a top-level key. In the updated runner and reporting scripts, token metrics are now correctly extracted and flattened.
