# DDIV Controlled Pilot Report: Local Ollama Coder Evaluation

> [!NOTE]
> **Evaluation Framework Scope:**
> All evaluations reported herein are **Tier-1 Internal Reproductions** using SWE-bench Verified task data,
> exact target FAIL_TO_PASS test execution, and PASS_TO_PASS regression suites in isolated repository environments.
> These represent controlled experimental metrics under DDIV and are not official SWE-bench leaderboard submissions.

## 1. Experimental Configuration
- **Coder Model (Treatment):** `qwen2.5-coder:7b` (Local Ollama at `http://localhost:11434`)
- **Zero Fallback Guarantee:** Pure local Coder execution without cloud API fallback
- **Locator Agent:** `gemini-3.1-flash-lite`
- **Test Understanding / Supervisor / Critic / Tester:** `qwen/qwen3.8-27b` (Groq API)
- **Patch Builder:** Unified line-aligned, AST syntax-verified `DemoPatchBuilder`
- **Execution Timestamp:** `2026-10-13T16:54:33Z`

## 2. Condition Comparison Summary

| Condition | Completed Runs | Tier-1 Resolved | Resolution Rate | Pass@1 Count | Avg Tokens | Avg Wall-Clock (s) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **BASELINE** | 3/3 | 0/3 | **0.0%** | 0 | 8,857.0 | 180.5s |
| **RETRY_ONLY** | 3/3 | 0/3 | **0.0%** | 0 | 26,537.3 | 321.9s |
| **FULL_DDIV** | 3/3 | 1/3 | **33.3%** | 0 | 35,104.0 | 355.5s |

## 3. Detailed Per-Run Outcomes

| Task ID | Condition | Status | Resolved | Attempts | F2P Passed | P2P Passed | Tokens | Latency (s) | Failure / Stage |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| `pylint-dev__pylint-6903` | `BASELINE` | COMPLETED | ❌ NO | 1 | 0/1 | 8/8 | 9,564 | 228.4s | `F2P_FAILURE` |
| `pylint-dev__pylint-6903` | `RETRY_ONLY` | COMPLETED | ❌ NO | 3 | 0/0 | 0/0 | 28,152 | 323.0s | `ANCHOR_NOT_FOUND` |
| `pylint-dev__pylint-6903` | `FULL_DDIV` | COMPLETED | ✅ **YES** | 2 | 1/1 | 8/8 | 32,760 | 381.2s | `RESOLVED` |
| `pylint-dev__pylint-4970` | `BASELINE` | COMPLETED | ❌ NO | 1 | 0/1 | 0/10 | 9,395 | 131.7s | `PATCH_INVALID` |
| `pylint-dev__pylint-4970` | `RETRY_ONLY` | COMPLETED | ❌ NO | 3 | 0/0 | 0/0 | 27,809 | 268.7s | `ANCHOR_NOT_FOUND` |
| `pylint-dev__pylint-4970` | `FULL_DDIV` | COMPLETED | ❌ NO | 3 | 0/0 | 0/0 | 38,715 | 243.7s | `PATCH_INVALID` |
| `sympy__sympy-23413` | `BASELINE` | COMPLETED | ❌ NO | 1 | 0/1 | 2/2 | 7,612 | 181.4s | `F2P_FAILURE` |
| `sympy__sympy-23413` | `RETRY_ONLY` | COMPLETED | ❌ NO | 3 | 0/1 | 2/2 | 23,651 | 374.0s | `REPEATED_PATCH_CYCLE` |
| `sympy__sympy-23413` | `FULL_DDIV` | COMPLETED | ❌ NO | 3 | 0/0 | 0/0 | 33,837 | 441.7s | `ANCHOR_NOT_FOUND` |