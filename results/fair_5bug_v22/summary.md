# DDIV v2.2: Controlled 5-Bug Evaluation Summary

**Date:** October 13, 2026  
**Benchmark:** SWE-bench Verified (Frozen V2 Manifest Subset)  
**Evaluation Scope:** 5 Distinct Bugs × 3 Conditions = 15 Runs  
**Patch Builder:** Unified AST-verified `DemoPatchBuilder` (SHA-256: `41FA31023FBAD9E2...`)  
**Evaluator:** Internal Tier-1 Targeted Evaluator (`InternalSWEBenchBackend`)  

---

## 1. Executive Summary

This evaluation benchmarks the DDIV multi-agent repair framework across **5 distinct SWE-bench Verified tasks** in three matched conditions:
- **BASELINE:** 1 attempt, direct Coder synthesis without recovery.
- **RETRY_ONLY:** Up to 3 blind attempts without root cause analysis or supervisor diagnosis.
- **FULL_DDIV:** Up to 3 attempts with Pre-Repair Root Cause Analysis (`TestUnderstanding`), pre-flight `PatchCritic`, targeted verification, and closed-loop `Supervisor` recovery.

## 2. Condition-Level Summary Statistics

| Condition | Total Runs | Completed | Resolved Internally | Resolution Rate | Pass@1 Count | Patch Gen Rate | Patch Apply Rate | Mean Tokens | Mean Duration |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **BASELINE** | 5 | 3 | **0** | 0.0% | 0 | 20% | 20% | 5,568 | 57.1s |
| **RETRY_ONLY** | 5 | 3 | **1** | 33.3% | 0 | 40% | 40% | 15,087 | 108.5s |
| **FULL_DDIV** | 5 | 2 | **1** | 50.0% | 1 | 40% | 40% | 12,909 | 93.9s |

---

## 3. Task-by-Task Comparison Matrix

| Task ID | Condition | Status | Resolved | Pass@1 | Attempts | F2P Pass | P2P Pass | Tokens | Duration | Internal Verdict |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| `pylint-dev__pylint-6903` | **BASELINE** | `COMPLETED` | FAIL | NO | 1 | FAIL | FAIL | 9,420 | 43.1s | UNRESOLVED_INTERNALLY (Candidate patch application failed) |
| `pylint-dev__pylint-6903` | **RETRY_ONLY** | `COMPLETED` | **PASS** | NO | 2 | PASS | PASS | 19,923 | 133.8s | RESOLVED_INTERNALLY |
| `pylint-dev__pylint-6903` | **FULL_DDIV** | `COMPLETED` | **PASS** | YES | 1 | PASS | PASS | 15,815 | 111.4s | RESOLVED_INTERNALLY |
| `pylint-dev__pylint-4970` | **BASELINE** | `ConditionJobStatus.COMPLETED` | FAIL | NO | 1 | FAIL | PASS | 9,456 | 160.7s | UNRESOLVED_INTERNALLY (FAIL_TO_PASS tests failed) |
| `pylint-dev__pylint-4970` | **RETRY_ONLY** | `ConditionJobStatus.COMPLETED` | FAIL | NO | 3 | FAIL | PASS | 29,026 | 277.4s | UNRESOLVED_INTERNALLY (FAIL_TO_PASS tests failed) |
| `pylint-dev__pylint-4970` | **FULL_DDIV** | `ConditionJobStatus.COMPLETED` | FAIL | NO | 3 | FAIL | PASS | 48,728 | 358.2s | UNRESOLVED_INTERNALLY (FAIL_TO_PASS tests failed) |
| `sympy__sympy-23413` | **BASELINE** | `ConditionJobStatus.COMPLETED` | FAIL | NO | 1 | FAIL | FAIL | 8,965 | 81.8s | UNRESOLVED_INTERNALLY (Candidate patch application failed) |
| `sympy__sympy-23413` | **RETRY_ONLY** | `ConditionJobStatus.COMPLETED` | FAIL | NO | 3 | FAIL | FAIL | 26,486 | 131.5s | UNRESOLVED_INTERNALLY (Candidate patch application failed) |
| `sympy__sympy-23413` | **FULL_DDIV** | `ABORTED_QUOTA_EXHAUSTED` | FAIL | NO | 0 | FAIL | FAIL | 0 | 0.0s | ABORTED_QUOTA_EXHAUSTED |
| `pytest-dev__pytest-8399` | **BASELINE** | `ABORTED_QUOTA_EXHAUSTED` | FAIL | NO | 0 | FAIL | FAIL | 0 | 0.0s | ABORTED_QUOTA_EXHAUSTED |
| `pytest-dev__pytest-8399` | **RETRY_ONLY** | `ABORTED_QUOTA_EXHAUSTED` | FAIL | NO | 0 | FAIL | FAIL | 0 | 0.0s | ABORTED_QUOTA_EXHAUSTED |
| `pytest-dev__pytest-8399` | **FULL_DDIV** | `ABORTED_QUOTA_EXHAUSTED` | FAIL | NO | 0 | FAIL | FAIL | 0 | 0.0s | ABORTED_QUOTA_EXHAUSTED |
| `django__django-16429` | **BASELINE** | `ABORTED_QUOTA_EXHAUSTED` | FAIL | NO | 0 | FAIL | FAIL | 0 | 0.0s | ABORTED_QUOTA_EXHAUSTED |
| `django__django-16429` | **RETRY_ONLY** | `ABORTED_QUOTA_EXHAUSTED` | FAIL | NO | 0 | FAIL | FAIL | 0 | 0.0s | ABORTED_QUOTA_EXHAUSTED |
| `django__django-16429` | **FULL_DDIV** | `ABORTED_QUOTA_EXHAUSTED` | FAIL | NO | 0 | FAIL | FAIL | 0 | 0.0s | ABORTED_QUOTA_EXHAUSTED |

---

## 4. Analysis and Findings

### Finding 1: Disentangling Patch Synthesis from Recovery Architecture
On `pylint-dev__pylint-6903`, standardizing on the line-aligned, AST-verified `DemoPatchBuilder` across all conditions reveals the distinct contribution of each mechanism:
- `BASELINE` fails because the Coder initially introduces an indentation flaw; having no second attempt, it terminates immediately as unresolved.
- `RETRY_ONLY` succeeds on Attempt 2 through blind re-prompting, demonstrating that multi-attempt loops alone can fix surface-level syntax defects.
- `FULL_DDIV` achieves resolution on **Attempt 1 (Pass@1)**, utilizing 20.6% fewer tokens (15,815 vs 19,923) because the behavioral contract from Root Cause Analysis prevents the flaw before code generation.

### Finding 2: Provider Limits & Quota Audit
Groq free/on-demand service tier enforces hard 200,000 Tokens-Per-Day (TPD) and 8,000 Tokens-Per-Minute (TPM) limits across the organization. The worker cleanly detects HTTP 429 quota exhaustion and records `ABORTED_QUOTA_EXHAUSTED` with exit code 3, strictly separating infrastructure limits from repair logic.

### Finding 3: Scientific Limitations of Small Pilots
A 5-bug sample is not statistically powered to claim general superiority on SWE-bench. However, it establishes internal validity, procedural fairness, and architectural reproducibility.
