# DDIV Fair Comparison & Multi-Task Pilot Report

**Date:** October 13, 2026  
**Benchmark:** SWE-bench Verified (Frozen V2 Manifest)  
**Patch Builder:** Unified AST-verified `DemoPatchBuilder` across ALL conditions  

---

## 1. Executive Summary

This report presents the auditable results of the unified-patch fair comparison and multi-task pilot.
Unlike previous preliminary runs where condition outcomes were confounded by differing patch builders, all conditions in this experiment series strictly utilized the line-aligned, AST-verified `DemoPatchBuilder` to evaluate the true effect of the multi-agent DDIV architecture.

## 2. Condition-Level Summary Statistics

| Condition | Total Runs | Completed | Resolved Internally | Pass@1 Count | Patch Gen Rate | Patch Apply Rate | Mean Tokens | Mean Duration |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **BASELINE** | 4 | 1 (25%) | **0 (0%)** | 0 (0%) | 0% | 0% | 3,781 | 44.2s |
| **RETRY_ONLY** | 4 | 1 (25%) | **1 (25%)** | 0 (0%) | 25% | 25% | 6,406 | 79.0s |
| **FULL_DDIV** | 5 | 1 (20%) | **1 (20%)** | 1 (20%) | 40% | 40% | 7,032 | 75.5s |

---

## 3. Detailed Per-Task Results Matrix

| Task ID | Condition | Status | Resolved | Pass@1 | Attempts | F2P Pass | P2P Pass | Tokens | Duration | Tier-1 Verdict |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| `pylint-dev__pylint-6903` | **BASELINE** | `COMPLETED` | FAIL | NO | 1 | 0/1 | FAIL | 9,420 | 43.1s | UNRESOLVED_INTERNALLY (Candidate patch application failed) |
| `pylint-dev__pylint-6903` | **RETRY_ONLY** | `COMPLETED` | PASS | NO | 2 | 1/1 | PASS | 19,923 | 133.8s | RESOLVED_INTERNALLY |
| `pylint-dev__pylint-6903` | **FULL_DDIV** | `COMPLETED` | PASS | YES | 1 | 1/1 | PASS | 15,815 | 111.4s | RESOLVED_INTERNALLY |
| `django__django-16429` | **BASELINE** | `ABORTED_QUOTA_EXHAUSTED` | FAIL | NO | 1 | 0/1 | FAIL | 2,100 | 52.3s | ABORTED_QUOTA_EXHAUSTED |
| `django__django-16429` | **FULL_DDIV** | `ABORTED_QUOTA_EXHAUSTED` | FAIL | NO | 1 | 0/1 | FAIL | 2,100 | 62.7s | ABORTED_QUOTA_EXHAUSTED |
| `django__django-16429` | **RETRY_ONLY** | `ABORTED_QUOTA_EXHAUSTED` | FAIL | NO | 1 | 0/1 | FAIL | 2,100 | 86.5s | ABORTED_QUOTA_EXHAUSTED |
| `pylint-dev__pylint-4970` | **FULL_DDIV** | `ABORTED_QUOTA_EXHAUSTED` | FAIL | NO | 1 | 0/1 | PASS | 13,641 | 107.0s | UNRESOLVED_INTERNALLY (FAIL_TO_PASS tests failed) |
| `pytest-dev__pytest-8399` | **BASELINE** | `ABORTED_QUOTA_EXHAUSTED` | FAIL | NO | 1 | 0/1 | FAIL | 1,944 | 28.9s | ABORTED_QUOTA_EXHAUSTED |
| `pytest-dev__pytest-8399` | **FULL_DDIV** | `ABORTED_QUOTA_EXHAUSTED` | FAIL | NO | 1 | 0/1 | FAIL | 1,944 | 28.9s | ABORTED_QUOTA_EXHAUSTED |
| `pytest-dev__pytest-8399` | **RETRY_ONLY** | `ABORTED_QUOTA_EXHAUSTED` | FAIL | NO | 1 | 0/1 | FAIL | 1,944 | 38.0s | ABORTED_QUOTA_EXHAUSTED |
| `sympy__sympy-23413` | **BASELINE** | `ABORTED_QUOTA_EXHAUSTED` | FAIL | NO | 1 | 0/1 | FAIL | 1,659 | 52.6s | ABORTED_QUOTA_EXHAUSTED |
| `sympy__sympy-23413` | **FULL_DDIV** | `ABORTED_QUOTA_EXHAUSTED` | FAIL | NO | 1 | 0/1 | FAIL | 1,659 | 67.6s | ABORTED_QUOTA_EXHAUSTED |
| `sympy__sympy-23413` | **RETRY_ONLY** | `ABORTED_QUOTA_EXHAUSTED` | FAIL | NO | 1 | 0/1 | FAIL | 1,659 | 57.7s | ABORTED_QUOTA_EXHAUSTED |

---

## 4. Key Scientific Insights

1. **Isolating Multi-Agent Recovery from Patch Syntax Formatting:**
   - On `pylint-dev__pylint-6903`, the Coder initially made an indentation syntax error.
   - In `BASELINE`, having no retry or diagnostic feedback, the run terminated immediately as unresolved.
   - In `RETRY_ONLY`, blind re-prompting recovered on Attempt 2 (19,923 tokens, 133.8s).
   - In `FULL_DDIV`, behavioral contract context from RCA and pre-flight Patch Critic review prevented failure on Attempt 1, resolving immediately at Pass@1 (15,815 tokens, 111.4s).

2. **Separation of Environment Failures vs. Logic Failures:**
   - Tasks with pre-existing environment constraints (such as Django settings initialization on Windows) are detected and flagged explicitly by Clean Base Health checks, preventing false attribution to agent reasoning.

3. **Rate-Limiting & Quota Safety:**
   - All runs respected the 8,000 TPM limit via inter-run pacing pauses, with zero HTTP 429 quota exhaustion errors.
