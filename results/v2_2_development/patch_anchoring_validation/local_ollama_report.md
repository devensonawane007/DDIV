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
- **Execution Timestamp:** `2026-10-14T14:15:01Z`

## 2. Condition Comparison Summary

| Condition | Completed Runs | Tier-1 Resolved | Resolution Rate | Pass@1 Count | Avg Tokens | Avg Wall-Clock (s) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **BASELINE** | 0/2 | 0/0 | **N/A** | 0 | 0 | 0.0s |
| **RETRY_ONLY** | 0/2 | 0/0 | **N/A** | 0 | 0 | 0.0s |
| **FULL_DDIV** | 2/2 | 0/2 | **0.0%** | 0 | 40,289.5 | 327.3s |

## 3. Detailed Per-Run Outcomes

| Task ID | Condition | Status | Resolved | Attempts | F2P Passed | P2P Passed | Tokens | Latency (s) | Failure / Stage |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| `pylint-dev__pylint-6903` | `FULL_DDIV` | COMPLETED | ❌ NO | 3 | 0/1 (Not Run - Apply Failed) | 0/8 (Not Run - Apply Failed) | 47,178 | 375.1s | `PATCH_APPLICATION_FAILED` |
| `pylint-dev__pylint-4970` | `FULL_DDIV` | COMPLETED | ❌ NO | 3 | 0/1 | 0/10 | 33,401 | 279.6s | `P2P_REGRESSION` |