# DDIV v2.1: Research Paper Claims Checklist & Empirical Grounding

**Audit Date:** October 13, 2026  
**Purpose:** Independent evaluation of core research claims against verified experimental data. Identifies supported, preliminary, confounded, and unsupported claims to ensure paper submission integrity.

---

## 1. Summary Matrix of Paper Claims

| # | Research Claim | Empirical Status | Recommendation for Paper |
| :-: | :--- | :---: | :--- |
| **1** | *"DDIV achieves a 40.0% Task Success Rate on SWE-bench Verified tasks."* | **UNSUPPORTED / CONFOUNDED** | **MUST REMOVE OR REQUALIFY**. The 40% (2/5) was recorded strictly under the deterministic mock test harness (`dev_validation_001`). Under real LLMs, resolution is 0/X (0.0%). |
| **2** | *"Full DDIV outperforms Baseline and Retry-Only on real SWE-bench Verified resolutions."* | **UNSUPPORTED** | **MUST REMOVE**. Across all real-provider experiments (`benchmark_v2_1_batch_1`, 3-task validations, and ablation), internal Tier-1 resolution is 0% across ALL conditions. |
| **3** | *"Closed-loop diagnostic feedback significantly increases candidate patch generation rates."* | **SUPPORTED** | **RETAIN & EMPHASIZE**. Full DDIV generated patches on 100% of tasks (3/3) in Batch 1 compared to 33.3% (1/3) for Baseline and Retry-Only. |
| **4** | *"The deterministic Failure Detector achieves high-fidelity taxonomy classification ($F1–F4$)."* | **SUPPORTED (Preliminary)** | **RETAIN AS ARCHITECTURAL CONTRIBUTION**. Deterministic classification correctly differentiated $F1$, $F2$, and $F3$ across evaluated jobs. Sample size is small ($N=3–5$ tasks). |
| **5** | *"The primary bottleneck preventing software bug resolution is the coder model choice."* | **REFUTED** | **REPLACE WITH NEGATIVE RESULT**. Controlled ablation showed 0/3 resolution for both GPT-OSS 120B and Gemini 3.8 Flash, proving coder choice is not the sole bottleneck. |
| **6** | *"Dynamic Trust Ledgers effectively steer multi-agent recovery and penalize regressions."* | **PRELIMINARY / MECHANISTIC** | **REQUALIFY**. The trust ledger mechanism is mathematically and computationally verified in SQLite, but its impact on resolution rate is unproven due to 0% real resolution. |
| **7** | *"Open-source / on-demand LLMs can support full closed-loop SWE-bench evaluation without paid quotas."* | **REFUTED** | **DOCUMENT AS CORE LIMITATION**. Groq on-demand quotas (200k TPD, 8k TPM) and Gemini free tier (20 req/day) severely confound multi-turn recovery benchmarks. |

---

## 2. Detailed Claim-by-Claim Breakdown

### Claim 1: "DDIV achieves a 40.0% Task Success Rate (2/5) on SWE-bench Verified"
* **Original Context**: Stated in development set validation documentation (`walkthrough.md` line 87).
* **Empirical Evidence**:
  - `dev_validation_001` result JSON inspection reveals:
    `"model": "mock-locator"`, `"model": "mock-rca"`, `"model": "mock-coder"`, and mocked file `src/calculator.py`.
  - In `dev_validation_001`, the pipeline ran with deterministic synthetic agents simulating an $F2 \to A2$ recovery loop.
  - Across all real LLM runs (`openai/gpt-oss-120b`, `qwen/qwen3.8-27b`, `gemini-3.1-flash-lite`, `gemini-3.8-flash`), **zero tasks were resolved (0/X, 0.0%)** against official test suites.
* **Paper Action**:
  - **Do NOT cite 40% as an LLM resolution rate.**
  - If mentioned at all, label it strictly as *"Pipeline Integration Verification on Mock Injected Scenarios"*.

---

### Claim 2: "Full DDIV outperforms Baseline and Retry-Only on Bug Resolution"
* **Original Context**: Hypothesis that closed-loop diagnosis enables real bug resolution where blind retry fails.
* **Empirical Evidence**:
  - `benchmark_v2_1_batch_1`: Baseline 0/3 (0.0%), Retry-Only 0/3 (0.0%), Full-DDIV 0/3 (0.0%).
  - `validation_3tasks_v21_20261009`: Baseline 0/3 (0.0%), Retry-Only 0/3 (0.0%), Full-DDIV 0/3 (0.0%).
  - `validation_3tasks_v21_post_provider_fix_20261012`: Baseline 0/3 (0.0%), Retry-Only 0/3 (0.0%), Full-DDIV 0/3 (0.0%).
  - `validation_3tasks_v21_django_repair_20261012`: Baseline 0/1 (0.0%), Retry-Only 0/1 (0.0%), Full-DDIV 0/1 (0.0%).
* **Paper Action**:
  - Acknowledge honestly that on SWE-bench Verified repositories, resolution rate remains 0.0% across all three experimental conditions.
  - Reframe comparison around **intermediate milestone progression**: patch synthesis, patch application, and diagnostic precision.

---

### Claim 3: "Closed-Loop Feedback Improves Candidate Patch Generation Efficacy"
* **Original Context**: Supervisory recovery guides the coder to produce valid candidate patches.
* **Empirical Evidence**:
  - In `benchmark_v2_1_batch_1`:
    - `baseline`: 1/3 tasks produced a patch (33.3%).
    - `retry_only`: 1/3 tasks produced a patch (33.3%).
    - `full_ddiv`: **3/3 tasks produced patches (100.0%)**.
  - In `coder_ablation_v21_20261012`:
    - `full_ddiv__coder_a` produced patches on 2/3 tasks (66.7%) and applied them cleanly to 2/3 repositories.
* **Paper Action**:
  - **Supported and Defensible**. Highlight that closed-loop diagnostic feedback significantly improves the pipeline's ability to locate symbols, extract verbatim anchors, and emit valid unified diffs over multiple turns.
  - Pair with the central thesis: **"Valid Patch ≠ Correct Patch"**.

---

### Claim 4: "Deterministic Failure Classification ($F1–F4$) High Fidelity"
* **Original Context**: Deterministic classification eliminates ambiguous LLM-based post-hoc evaluation.
* **Empirical Evidence**:
  - When test suites failed, the Failure Detector accurately classified:
    - $F2$ (Code/Reasoning failure) on `psf__requests-2931` and `pylint-dev__pylint-6903`.
    - $F3$ (Tool/Execution anchor failure) on `mwaskom__seaborn-3187`.
  - Zero misclassifications observed between code logic and tool execution failures on clean runs.
* **Paper Action**:
  - Retain as a core systems contribution. Highlight that deterministic failure detection avoids LLM hallucination during recovery diagnosis. Note small sample size ($N=3–5$ tasks).

---

### Claim 5: "The Coder Model is the Primary Bottleneck Preventing Resolution"
* **Original Context**: Hypothesis that substituting Groq GPT-OSS 120B with Google Gemini 3.8 Flash would unlock bug resolution.
* **Empirical Evidence**:
  - `coder_ablation_v21_20261012`:
    - Coder A (`openai/gpt-oss-120b`): 0/3 resolved, 2/3 patches generated, 2/3 patches applied.
    - Coder B (`gemini-3.8-flash`): 0/3 resolved, 0/3 patches generated, 0/3 patches applied.
  - Gemini failed Attempt 1 due to reasoning token budget starvation cutting off output after ~160 visible tokens, and failed subsequent attempts due to Google Cloud free-tier request limits.
* **Paper Action**:
  - Present as a **valuable empirical ablation and negative result**: swapping the coder model did not solve the benchmark. The bottleneck lies in complex multi-index semantics, exact verbatim AST anchor matching, and deep repository test harnesses.

---

### Claim 6: "Dynamic Trust Ledgers Steer Multi-Agent Recovery"
* **Original Context**: Dynamic trust score adjustments penalize regressions and guide agent delegation.
* **Empirical Evidence**:
  - The SQLite trust ledger correctly adjusts scores (`TRUST_FAILURE_DELTA = 0.08`, `TRUST_REGRESSION_DELTA = 0.10`).
  - However, because no real bug was resolved, trust scores monotonically degraded across attempts.
* **Paper Action**:
  - Frame trust ledgers as an architectural safety mechanism that successfully captures regressions, rather than a proven driver of empirical resolution gains.

---

## 3. Confounding Experimental Factors (Mandatory Paper Limitations)

The paper must transparently disclose the following infrastructural confounds:

1. **Provider Quotas and Token Ceilings**:
   - **Groq 8,000 TPM limit**: Prevented Attempt 3 execution on `pydata__xarray-7393__full_ddiv` when cumulative context reached 8,332 tokens.
   - **Groq 200,000 TPD limit**: Constrained multi-task benchmarking to small batches.
   - **Google Gemini 20 req/day limit**: Completely blocked extended multi-attempt ablation testing on `gemini-3.8-flash`.
2. **Reasoning Token Overhead**:
   - Modern reasoning models (e.g. Gemini thinking models) consume thousands of hidden tokens for internal deliberation, starving visible output budgets unless `max_tokens` is configured above 8,192 and `reasoning_effort` is explicitly bounded.
3. **Operating System File Path Limits**:
   - Windows default `MAX_PATH` (260 characters) caused Git checkout failures on deep workspace directories (`django__django-16429`) until `core.longpaths = true` was configured.
