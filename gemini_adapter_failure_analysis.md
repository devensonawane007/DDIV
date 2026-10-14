# DDIV v2.1: Gemini Coder Adapter Failure Analysis & Forensic Investigation

**Date:** 2026-10-12 / 2026-10-13  
**System:** DDIV (Detect → Diagnose → Intervene → Verify) v2.1  
**Target Adapter:** Isolated Gemini Coder Adapter (`scripts/gemini_coder_adapter.py`)  
**Investigated Experiment:** `coder_ablation_v21_20261012`  
**Endpoint:** `https://generativelanguage.googleapis.com/v1beta/openai/`  
**Target Model:** `gemini-3.8-flash`  

---

## 1. Executive Summary

During the initial Coder Model Ablation (`coder_ablation_v21_20261012`), Coder B (`gemini-3.8-flash`) failed across all three evaluated Batch 1 tasks (`pylint-dev__pylint-6903`, `mwaskom__seaborn-3187`, `pydata__xarray-7393`), generating **0/3** valid candidate patches.

This forensic analysis diagnosed the exact failure mechanisms across request construction, token consumption, response parsing, and provider quota limits.

---

## 2. Forensic Analysis of Failure Modes

### Question 1: Did Gemini return JSON, Markdown-fenced JSON, or conversational prose?
* **Confirmed Observation**:
  - In `mwaskom__seaborn-3187` (Attempt 1): Gemini returned unformatted conversational prose starting with raw array expressions:
    `['axes.formatter.useoffset']\nmpl.rcParams['axes.formatter.offset_threshold']\nHowever, I did not test it...`
  - In `mwaskom__seaborn-3187` (Attempt 3): Gemini returned conversational reasoning with code fences:
    `...\n```\nWait! Let's check what axis.major.formatter is and what happens there in Continuous._setup:\n...`
  - In `pylint-dev__pylint-6903` (Attempts 1 and 2) and `pydata__xarray-7393` (Attempt 1): Gemini began generating a valid JSON object starting with:
    `{\n  "behavioral_analysis": "..."`
    However, the JSON object was abruptly truncated mid-stream.

### Question 2: Did the request use a supported structured-output option?
* **Confirmed Observation**:
  - In the original `OpenAICompatibleProvider`, the request configured `kwargs["response_format"] = {"type": "json_object"}` and appended the stringified Pydantic schema to the user message.
  - It did **not** use native OpenAI Structured Outputs (`response_format={"type": "json_schema", "json_schema": {"name": "CoderOutput", "schema": ...}}`).
  - Setting only `{"type": "json_object"}` requests generic JSON syntax without grammar-guided schema enforcement. This allowed the model to produce unconstrained text in `seaborn-3187`.

### Question 3: Was response content extracted from the correct field?
* **Confirmed Observation**:
  - Content was correctly extracted from `response.choices[0].message.content`.
  - However, `response.choices[0].finish_reason` was **never inspected**. When the model hit `finish_reason == "length"` (truncation), the truncated text was forwarded directly to `extract_json_from_text()`, which failed with a generic `INVALID_RESPONSE` error.

### Question 4: Did the extracted object fail Pydantic validation, and which fields failed?
* **Confirmed Observation**:
  - Execution never reached `CoderOutput.model_validate()`.
  - Because outputs were either non-JSON prose (`seaborn`) or truncated JSON strings (`pylint`, `xarray`), `extract_json_from_text()` returned `None`.
  - The pipeline failed at the initial JSON parsing stage (`[CODER_API_ERROR] Failed to extract valid JSON matching schema from output`).

### Question 5: Did token limits or response truncation contribute?
* **Confirmed Observation (Primary Technical Root Cause)**:
  - **Yes. Token starvation caused by reasoning/thinking tokens was the primary root cause of JSON syntax failures.**
  - `gemini-3.8-flash` is a reasoning model that generates internal thinking tokens prior to emitting visible text.
  - In `scripts/run_coder_ablation_worker.py`, `max_tokens` was configured to `4096` with no `reasoning_effort` constraint.
  - Across the ablation invocations, Google API token accounting records:
    - `pylint-dev` (Attempt 1): `prompt_tokens`: 4255, `completion_tokens`: 161, `total_tokens`: 8344. Total generation = 8344 - 4255 = **4089 tokens**.
    - `pylint-dev` (Attempt 2): `prompt_tokens`: 4618, `completion_tokens`: 161, `total_tokens`: 8707. Total generation = 8707 - 4618 = **4089 tokens**.
    - `seaborn` (Attempt 1): `prompt_tokens`: 4884, `completion_tokens`: 162, `total_tokens`: 8976. Total generation = 8976 - 4884 = **4092 tokens**.
    - `seaborn` (Attempt 3): `prompt_tokens`: 5426, `completion_tokens`: 161, `total_tokens`: 9518. Total generation = 9518 - 5426 = **4092 tokens**.
  - In every invocation, the combined token count (thinking tokens + completion tokens) reached the 4096 ceiling. The model spent ~3,928 tokens on internal thinking, leaving only ~160 visible tokens before being abruptly cut off.
  - The JSON object was truncated mid-sentence, guaranteeing that `json.loads` would fail.

### Question 6: Which HTTP 429 errors occurred?
* **Confirmed Observation**:
  Two separate 429-related phenomena occurred:
  1. **False Quota Exhaustion Detection**:
     In `pylint-dev__pylint-6903` Attempt 2, the truncated JSON string contained the problem statement token `cpu.cfs_quota_us`. The runner's `_is_quota_exhausted()` scanned the entire error message for `"quota"`, misclassifying a syntax truncation as `ABORTED_QUOTA_EXHAUSTED`.
  2. **Actual Google AI Studio Free-Tier Limit**:
     In `pydata__xarray-7393` Attempt 2 and the live smoke test, Gemini returned an actual HTTP 429 (`ResourceExhausted`):
     ```text
     Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-3.8-flash
     quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier, quotaValue: 20
     ```
     This confirms that `gemini-3.8-flash` on this Google Cloud project is subject to a hard free-tier ceiling of **20 requests per day**.

---

## 3. Confirmed Observations vs. Hypotheses

| Topic | Status | Evidence |
| :--- | :---: | :--- |
| **Thinking token consumption** | **Confirmed** | Total generation tokens consistently capped at 4,089–4,092 with only ~161 completion tokens recorded. |
| **JSON syntax failure cause** | **Confirmed** | Direct truncation due to max_tokens ceiling prevented complete JSON object generation. |
| **False quota trigger** | **Confirmed** | Word `"quota"` in `cpu.cfs_quota_us` triggered `_is_quota_exhausted()`. |
| **Daily request limit** | **Confirmed** | Google RPC `QuotaFailure` explicitly cites `quotaValue: 20` and `limit: 20` per day for `gemini-3.8-flash`. |
| **Gemini code repair capability** | **Inconclusive** | Because the model was truncated and rate-limited, zero valid patches could be evaluated against test suites. |

---

## 4. Operational Recommendations

1. **Adapter-Level Bounded Reasoning & Headroom**:
   In `scripts/gemini_coder_adapter.py`, configure `reasoning_effort="low"` and `max_tokens=8192` (or 16384) to allocate sufficient generation headroom for `CoderOutput`.
2. **Native Structured Outputs**:
   Pass `response_format={"type": "json_schema", ...}` to guarantee valid JSON formatting without conversational preamble.
3. **Daily Quota Ceiling Awareness**:
   Free-tier usage of `gemini-3.8-flash` cannot support continuous multi-attempt benchmarks (20 req/day limit). For extended experimentation, either a paid project tier or a model with higher free-tier throughput must be utilized.
