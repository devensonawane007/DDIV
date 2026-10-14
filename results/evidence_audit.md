# DDIV v2.1: Comprehensive Research Evidence Audit

**Audit Date:** October 13, 2026  
**Pipeline:** DDIV (Detect → Diagnose → Intervene → Verify) Research Framework  
**Scope:** Complete consolidation of all historical validation, benchmark, and ablation records  
**Integrity Guarantee:** All reported outcomes verified directly against saved structured result JSON files and evaluator records. No results merged across differing experimental protocols, model configurations, or task sets.

---

## 1. Executive Summary

This audit consolidates all empirical evidence gathered across the DDIV v2.1 research pipeline into a single, auditable evidence package. 

### Key Findings
1. **The Mock Integration Test vs. Real Model Resolution Gap**:
   - The previously cited **40.0% Task Success Rate (2/5 tasks resolved)** was recorded exclusively in `dev_validation_001` under the **deterministic mock provider** using synthetic recovery scenarios.
   - Across **all real-provider executions** on SWE-bench Verified repositories (`openai/gpt-oss-120b`, `qwen/qwen3.8-27b`, `gemini-3.1-flash-lite`, and `gemini-3.8-flash`), **zero tasks (0/X, 0.0%) were internally resolved** against official repository unit test suites.
2. **Patch Generation and Application Progress**:
   - Under real LLMs, the DDIV multi-agent architecture successfully located bug sites and generated structurally valid unified patches:
     - In `benchmark_v2_1_batch_1`, `FULL_DDIV` achieved a **100% patch generation rate (3/3 tasks)** compared to **33.3% (1/3)** for `BASELINE` and `RETRY_ONLY`.
     - In `coder_ablation_v21_20261012`, Coder A (`openai/gpt-oss-120b`) successfully applied candidate patches to repositories on **2/3 tasks (66.7%)**.
   - However, generated patches failed internal Tier-1 test suites (`FAIL_TO_PASS` failures, $F2$), demonstrating that **synthesizing plausible syntax is fundamentally distinct from achieving semantic correctness**.
3. **Severe Infrastructure and Provider Bottlenecks**:
   - Empirical validation on free / on-demand LLM tiers was severely constrained by external API ceilings:
     - **Groq On-Demand**: 200,000 Tokens/Day (TPD) ceiling and 8,000 Tokens/Minute (TPM) request window caused job aborts (`pydata__xarray-7393__full_ddiv` aborted due to 8,332 prompt tokens).
     - **Google Gemini Free Tier**: Hard cap of 20 requests/day per project per model caused HTTP 429 exhaustion (`RESOURCE_EXHAUSTED`).
     - **Gemini Thinking Starvation**: 4,096 `max_tokens` ceiling caused internal reasoning tokens (~3,928) to starve visible output, cutting JSON short at ~160 tokens.
     - **Windows OS MAX_PATH**: Deep experiment directory paths initially triggered Git checkout errors on `django__django-16429` until `core.longpaths` was resolved.

> [!NOTE]
> **Evaluation Disclaimer**: All evaluations in this document represent **internal SWE-bench Tier-1 targeted evaluations** against isolated repository test harnesses. They do NOT constitute official SWE-bench Verified benchmark leaderboard submissions.

---

## 2. Granular Experiment Audit

### Experiment 1: `dev_validation_001` (Mock Integration Baseline)
- **Execution Date:** 2026-10-08
- **Provider Mode:** `MOCK` (Deterministic role-based test harness using synthetic calculator scenarios)
- **Task Set (5 tasks):** `astropy__astropy-12907`, `astropy__astropy-13033`, `pytest-dev__pytest-5221`, `psf__requests-2148`, `django__django-16429`
- **Conditions:** `baseline`, `retry_only`, `full_ddiv` (15 total jobs)

#### Performance Metrics

| Condition | Attempted | Completed | Timed Out | Failed / Aborted | Patch Generated | Patch Applied | Internal Tier-1 Resolved | Total Tokens | Total Runtime |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`baseline`** | 5 | 5 | 0 | 0 | 0/5 (0%)* | 0/5 (0%)* | **0/5 (0.0%)** | 3,000 | 47.2s |
| **`retry_only`** | 5 | 5 | 0 | 0 | 0/5 (0%)* | 0/5 (0%)* | **0/5 (0.0%)** | 9,000 | 80.2s |
| **`full_ddiv`** | 5 | 5 | 0 | 0 | 0/5 (0%)* | 0/5 (0%)* | **2/5 (40.0%)** | 14,600 | 66.2s |

*\*Note: In mock integration mode, simulated agents emitted diff strings directly into `generated_patch`, leaving structured `modifications` empty.*

#### Evaluator Verification
- `pytest-dev__pytest-5221__full_ddiv`: Resolved on Attempt 2 (Attempt 1 simulated $F2$ logic error, Attempt 2 simulated successful supervisor steering). Evaluator verdict: `RESOLVED_INTERNALLY`.
- `psf__requests-2148__full_ddiv`: Resolved on Attempt 2 via simulated exception handling patch. Evaluator verdict: `RESOLVED_INTERNALLY`.
- **Audit Conclusion**: Confirms that closed-loop supervisor diagnosis, failure classification, trust ledger adjustment, and multi-turn retry logic function correctly as an engineered software system. **This does not demonstrate LLM reasoning capability.**

---

### Experiment 2: `validation_3tasks_v21_20261009` (Real Providers Pilot)
- **Execution Date:** 2026-10-09
- **Provider Mode:** `REAL` (Groq `openai/gpt-oss-120b`, Groq `qwen/qwen3.8-27b`, Gemini `gemini-3.1-flash-lite`)
- **Task Set (3 tasks):** `psf__requests-2931`, `django__django-16429`, `sympy__sympy-23413`
- **Conditions:** `baseline`, `retry_only`, `full_ddiv` (9 total jobs)

#### Performance Metrics

| Condition | Attempted | Completed | Timed Out | Failed / Aborted | Patch Generated | Patch Applied | Internal Tier-1 Resolved | Total Tokens | Total Runtime |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`baseline`** | 3 | 3 | 0 | 0 | 0/3 (0.0%) | 0/3 (0.0%) | **0/3 (0.0%)** | 17,584 | 431.2s |
| **`retry_only`** | 3 | 3 | 0 | 0 | 0/3 (0.0%) | 0/3 (0.0%) | **0/3 (0.0%)** | 55,855 | 682.6s |
| **`full_ddiv`** | 3 | 3 | 0 | 0 | 0/3 (0.0%) | 0/3 (0.0%) | **0/3 (0.0%)** | 56,007 | 755.4s |

#### Evaluator Verification & Failure Analysis
- **`psf__requests-2931`**: Patches generated were evaluated against repository tests. `FAIL_TO_PASS` tests failed ($F2$).
- **`django__django-16429`**: Hit Groq 200k daily token limit during `FULL_DDIV` Attempt 2 (`Used 199,268 / Limit 200,000`).
- **`sympy__sympy-23413`**: Hit Groq 200k daily token limit during `BASELINE` (`Used 198,201 / Limit 200,000`).
- **Audit Conclusion**: Proved that unconstrained multi-attempt benchmarking rapidly exhausts Groq on-demand daily quotas (200k TPD). All 9 jobs exited cleanly, but 0/9 resolved.

---

### Experiment 3: `validation_3tasks_v21_post_provider_fix_20261012` (Post-Provider Fix)
- **Execution Date:** 2026-10-12
- **Provider Mode:** `REAL`
- **Task Set (3 tasks):** `psf__requests-2931`, `django__django-16429`, `sympy__sympy-23413`
- **Conditions:** `baseline`, `retry_only`, `full_ddiv` (9 total jobs)

#### Performance Metrics

| Condition | Attempted | Completed | Timed Out | Failed | Patch Generated | Patch Applied | Internal Tier-1 Resolved | Total Tokens | Total Runtime |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`baseline`** | 3 | 2 | 0 | 1 | 1/3 (33.3%) | 1/3 (33.3%) | **0/3 (0.0%)** | 16,512 | 182.9s |
| **`retry_only`** | 3 | 2 | 0 | 1 | 2/3 (66.7%) | 2/3 (66.7%) | **0/3 (0.0%)** | 52,160 | 421.6s |
| **`full_ddiv`** | 3 | 2 | 0 | 1 | 2/3 (66.7%) | 1/3 (33.3%) | **0/3 (0.0%)** | 96,820 | 801.2s |

#### Evaluator Verification & Failure Analysis
- **`django__django-16429`**: Failed in all 3 conditions before model inference due to Windows Git `MAX_PATH` limit (`Filename too long` during checkout).
- **`psf__requests-2931`**: Completed all attempts. In `full_ddiv`, generated and applied candidate patches, but failed internal `FAIL_TO_PASS` test harness (`test_prepared_request_body`).
- **`sympy__sympy-23413`**: Completed all attempts. In `full_ddiv`, generated candidate patches across 3 attempts, but anchor alignment failed on Attempt 1 and diff formatting failed on Attempts 2–3 ($F3$).
- **Audit Conclusion**: Zero model quota failures (57/57 model calls succeeded), but revealed Windows path length sensitivity. 0/9 resolved.

---

### Experiment 4: `validation_3tasks_v21_django_repair_20261012` (Django Isolated Repair)
- **Execution Date:** 2026-10-12
- **Provider Mode:** `REAL`
- **Task Set (1 task):** `django__django-16429`
- **Conditions:** `baseline`, `retry_only`, `full_ddiv` (3 total jobs post `git config --global core.longpaths true`)

#### Performance Metrics

| Condition | Attempted | Completed | Timed Out | Failed | Patch Generated | Patch Applied | Internal Tier-1 Resolved | Total Tokens | Total Runtime |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`baseline`** | 1 | 1 | 0 | 0 | 1/1 (100.0%) | 1/1 (100.0%) | **0/1 (0.0%)** | 8,544 | 117.3s |
| **`retry_only`** | 1 | 1 | 0 | 0 | 1/1 (100.0%) | 1/1 (100.0%) | **0/1 (0.0%)** | 26,529 | 252.9s |
| **`full_ddiv`** | 1 | 1 | 0 | 0 | 1/1 (100.0%) | 1/1 (100.0%) | **0/1 (0.0%)** | 50,016 | 413.1s |

#### Evaluator Verification
- Repository checkout succeeded cleanly in all 3 jobs.
- All 3 jobs generated and applied patches modifying Django ORM relationship instantiation logic.
- Evaluator executed official test suite `tests/model_inheritance/tests.py`. `FAIL_TO_PASS` tests failed in all attempts.
- **Audit Conclusion**: Fixed the environment checkout bug. Evaluator confirmed 0/3 resolved.

---

### Experiment 5: `benchmark_v2_1_batch_1` (Batch 1 Launch Execution)
- **Execution Date:** 2026-10-12
- **Provider Mode:** `REAL`
- **Task Set (3 tasks):** `pylint-dev__pylint-6903`, `mwaskom__seaborn-3187`, `pydata__xarray-7393`
- **Conditions:** `baseline`, `retry_only`, `full_ddiv` (9 total jobs)

#### Performance Metrics

| Condition | Attempted | Completed | Timed Out | Aborted (Quota) | Patch Generated | Patch Applied | Internal Tier-1 Resolved | Total Tokens | Total Runtime |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`baseline`** | 3 | 3 | 0 | 0 | 1/3 (33.3%) | 1/3 (33.3%) | **0/3 (0.0%)** | 30,594 | 306.8s |
| **`retry_only`** | 3 | 3 | 0 | 0 | 1/3 (33.3%) | 1/3 (33.3%) | **0/3 (0.0%)** | 97,146 | 669.0s |
| **`full_ddiv`** | 3 | 2 | 0 | 1 | **3/3 (100.0%)** | **2/3 (66.7%)** | **0/3 (0.0%)** | 160,857 | 1124.5s |

#### Evaluator Verification & Failure Analysis
- **`pylint-dev__pylint-6903`**: Candidate patches generated and applied across all conditions. Evaluator ran `tests/test_pylint_runners.py`. `FAIL_TO_PASS` tests failed in all attempts ($F2$).
- **`mwaskom__seaborn-3187`**: In `full_ddiv`, patch generated but anchor string `def get_legend_info(self):` failed exact-match insertion in `seaborn/_core/scales.py` ($F3$).
- **`pydata__xarray-7393`**: In `full_ddiv`, Attempt 1 and Attempt 2 generated and applied candidate patches, failing test suite ($F2 \to F4$). On Attempt 3, the cumulative prompt context reached 8,332 tokens, exceeding Groq's 8,000 Tokens/Minute limit (HTTP 413 `rate_limit_exceeded`), triggering job abort.
- **Audit Conclusion**: Full DDIV dramatically increased patch generation (100% vs 33.3%), but 0/3 resolved. Revealed Groq 8,000 TPM limit on multi-turn context expansion.

---

### Experiment 6: `coder_ablation_v21_20261012` (Controlled Coder Model Ablation)
- **Execution Date:** 2026-10-12
- **Provider Mode:** `REAL`
- **Condition:** `FULL_DDIV` (3 attempts max)
- **Comparison:** Coder A (Groq `openai/gpt-oss-120b`) vs Coder B (Google `gemini-3.8-flash`)
- **Task Set (3 tasks):** `pylint-dev__pylint-6903`, `mwaskom__seaborn-3187`, `pydata__xarray-7393` (6 total jobs)

#### Performance Metrics

| Condition / Variant | Attempted | Completed | Provider Error | Aborted (Quota) | Patch Generated | Patch Applied | Internal Tier-1 Resolved | Total Tokens | Total Runtime |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`full_ddiv__coder_a`** (GPT-OSS 120B) | 3 | 3 | 0 | 0 | **2/3 (66.7%)** | **2/3 (66.7%)** | **0/3 (0.0%)** | 171,614 | 1229.6s |
| **`full_ddiv__coder_b`** (Gemini 3.8 Flash) | 3 | 0 | 1 | 2 | **0/3 (0.0%)** | **0/3 (0.0%)** | **0/3 (0.0%)** | 127,408 | 789.3s |

#### Evaluator Verification & Failure Analysis
- **Coder A (`openai/gpt-oss-120b`)**: Reliably generated structured JSON edits. Applied clean patches to `pylint` and `xarray`. Evaluator ran official test suites; both failed `FAIL_TO_PASS` tests. Failed anchor matching on `seaborn`.
- **Coder B (`gemini-3.8-flash`)**: Failed in Attempt 1 on all tasks due to reasoning token starvation cutting off output after ~160 visible tokens (`Failed to extract valid JSON matching schema from output`). On subsequent attempts, Google AI Studio free-tier daily cap (20 requests/day per model) returned HTTP 429 (`RESOURCE_EXHAUSTED`).
- **Audit Conclusion**: Coder model is NOT the sole bottleneck. Replacing GPT-OSS 120B with Gemini 3.8 Flash did not improve resolution (0/3 vs 0/3) and degraded patch generation reliability (66.7% vs 0.0%).

---

### Experiment 7: Gemini Adapter Live Smoke Test (`gemini_smoke_result.json`)
- **Execution Date:** 2026-10-12T18:30:54Z
- **Model:** `gemini-3.8-flash` via isolated adapter [`scripts/gemini_coder_adapter.py`](file:///d:/DDIV/scripts/gemini_coder_adapter.py)
- **Configuration:** `max_tokens=8192`, `reasoning_effort="low"`, native `json_schema` response format.
- **Outcome:** **HTTP 429 (`RESOURCE_EXHAUSTED`)**. Quota error explicitly cited: `quotaMetric: generativelanguage.googleapis.com/generate_content_free_tier_requests`, `limit: 20`, `quotaValue: 20`.
- **Tokens Consumed:** 0 tokens. Latency: 15.96s.
- **Audit Conclusion**: Confirmed that Google Cloud Free Tier enforces an active 20 requests/day ceiling for `gemini-3.8-flash` on this project. Stop condition was triggered immediately.

---

## 3. Summary Performance Table Across All Experiments

| Experiment ID | Provider Mode | Tasks | Condition | Completed | Aborted / Failed | Patch Gen | Patch App | Resolved (Tier-1) | Total Tokens |
| :--- | :---: | :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `dev_validation_001` | Mock | 5 | `baseline` | 5/5 | 0/5 | 0/5 | 0/5 | **0/5 (0.0%)** | 3,000 |
| `dev_validation_001` | Mock | 5 | `retry_only` | 5/5 | 0/5 | 0/5 | 0/5 | **0/5 (0.0%)** | 9,000 |
| `dev_validation_001` | Mock | 5 | `full_ddiv` | 5/5 | 0/5 | 0/5 | 0/5 | **2/5 (40.0%)** | 14,600 |
| `validation_3tasks_20261009` | Real | 3 | `baseline` | 3/3 | 0/3 | 0/3 | 0/3 | **0/3 (0.0%)** | 17,584 |
| `validation_3tasks_20261009` | Real | 3 | `retry_only` | 3/3 | 0/3 | 0/3 | 0/3 | **0/3 (0.0%)** | 55,855 |
| `validation_3tasks_20261009` | Real | 3 | `full_ddiv` | 3/3 | 0/3 | 0/3 | 0/3 | **0/3 (0.0%)** | 56,007 |
| `validation_3tasks_20261012` | Real | 3 | `baseline` | 2/3 | 1/3 (MAX_PATH) | 1/3 | 1/3 | **0/3 (0.0%)** | 16,512 |
| `validation_3tasks_20261012` | Real | 3 | `retry_only` | 2/3 | 1/3 (MAX_PATH) | 2/3 | 2/3 | **0/3 (0.0%)** | 52,160 |
| `validation_3tasks_20261012` | Real | 3 | `full_ddiv` | 2/3 | 1/3 (MAX_PATH) | 2/3 | 1/3 | **0/3 (0.0%)** | 96,820 |
| `validation_django_repair` | Real | 1 | `baseline` | 1/1 | 0/1 | 1/1 | 1/1 | **0/1 (0.0%)** | 8,544 |
| `validation_django_repair` | Real | 1 | `retry_only` | 1/1 | 0/1 | 1/1 | 1/1 | **0/1 (0.0%)** | 26,529 |
| `validation_django_repair` | Real | 1 | `full_ddiv` | 1/1 | 0/1 | 1/1 | 1/1 | **0/1 (0.0%)** | 50,016 |
| `benchmark_v2_1_batch_1` | Real | 3 | `baseline` | 3/3 | 0/3 | 1/3 | 1/3 | **0/3 (0.0%)** | 30,594 |
| `benchmark_v2_1_batch_1` | Real | 3 | `retry_only` | 3/3 | 0/3 | 1/3 | 1/3 | **0/3 (0.0%)** | 97,146 |
| `benchmark_v2_1_batch_1` | Real | 3 | `full_ddiv` | 2/3 | 1/3 (TPM limit) | **3/3** | **2/3** | **0/3 (0.0%)** | 160,857 |
| `coder_ablation` | Real | 3 | `full_ddiv_coder_a` | 3/3 | 0/3 | **2/3** | **2/3** | **0/3 (0.0%)** | 171,614 |
| `coder_ablation` | Real | 3 | `full_ddiv_coder_b` | 0/3 | 3/3 (429/Error) | 0/3 | 0/3 | **0/3 (0.0%)** | 127,408 |
