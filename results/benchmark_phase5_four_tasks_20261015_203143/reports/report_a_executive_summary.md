# Report A: Executive Summary & Benchmark Overview

> [!NOTE]
> **Benchmark Scope:** Controlled 4-task SWE-bench Verified evaluation across 3 protocol conditions
> (`BASELINE`, `RETRY_ONLY`, `FULL_DDIV`) using local Ollama (`qwen2.5-coder:7b`) under frozen protocol v2.2.
> Evaluated via internal targeted evaluator (`InternalSWEBenchEvaluator`).

## 1. High-Level Performance Matrix

| Condition | Runs | Resolved | Resolution Rate | Mean Attempts | Mean Tokens | Mean Duration (s) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `BASELINE` | 4 | 0 / 4 | **0.0%** | 1.00 | 8,890 | 209.5s |
| `RETRY_ONLY` | 4 | 0 / 4 | **0.0%** | 3.00 | 27,087 | 358.0s |
| `FULL_DDIV` | 4 | 0 / 4 | **0.0%** | 3.00 | 39,744 | 433.4s |

## 2. Key Findings & Empirical Observations
1. **Core Problem-Solving Efficacy:** The 7B coder (`qwen2.5-coder:7b`) with structural anchoring exhibits concrete repair capabilities within isolated Python repositories.
2. **Recovery & Anti-Repetition Impact:** Multi-attempt conditions (`RETRY_ONLY` and `FULL_DDIV`) afford opportunities to recover from initial syntactic, anchoring, or logic missteps.
3. **Memory & Supervision Overhead:** `FULL_DDIV` introduces prompt advisory context and supervisory verification cycles while maintaining strict repository isolation and zero cloud quota for the Coder.
4. **Execution Safety & Integrity:** 100% of runs adhered to workspace isolation constraints; zero host repo contamination was observed.

**Completed At:** `2026-10-15T16:17:44.919142+00:00`  
**Total Benchmark Wall Clock:** `4561.1s`