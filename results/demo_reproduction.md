# DDIV End-to-End Demonstration Reproduction Guide

**Document Version:** 1.1  
**Date:** October 13, 2026  
**Target SWE-bench Task:** `pylint-dev__pylint-6903`  
**Internal Tier-1 Verdict:** `RESOLVED_INTERNALLY` (100% Pass)  
**Status:** FROZEN & AUDITED

---

## 1. Overview & Objective

This document provides the exact technical specification and reproduction procedures for the **DDIV (Detect, Diagnose, Intervene, Verify)** end-to-end software repair demonstration on **SWE-bench Verified**.

The demonstration resolves `pylint-dev__pylint-6903` by orchestrating a team of specialized foundation models to locate the root cause in `pylint/lint/run.py`, synthesize a minimal 1-line repair, construct a line-aligned AST-verified unified diff, and verify the patch against the official ground-truth test suite in an isolated workspace.

---

## 2. Multi-Agent Model Configuration

The demonstration uses the validated DDIV heterogeneous model allocation:

| Agent Role | Model ID | Provider | Parameters / Role Function |
| :--- | :--- | :--- | :--- |
| **Locator** | `gemini-3.1-flash-lite` | Google Gemini | High-context repository scan and file/symbol identification |
| **Test Understanding (RCA)** | `qwen/qwen3.8-27b` | Groq | Problem statement analysis and behavioral contract specification |
| **Coder** | `openai/gpt-oss-120b` | Groq | Structured code modification synthesis (`replace` / `insert_before`) |
| **Patch Critic** | `qwen/qwen3.8-27b` | Groq | Pre-execution safety review and regression risk scoring |
| **Tester** | `qwen/qwen3.8-27b` | Groq | Targeted test command recommendation |
| **Supervisor** | `qwen/qwen3.8-27b` | Groq | Failure categorization (F1?F6) and recovery strategy invocation (A1?A6) |

**Sampling Parameters:**
- `temperature`: `0.0` (deterministic greedy decoding)
- `seed`: `42`
- `max_tokens`: `4096`

---

## 3. Comparative Condition Results

The demonstration evaluates three conditions on the exact same task:

| Condition | Attempts | Result | Tier-1 Verdict | F2P Pass | P2P Pass | Total Tokens | Duration |
| :--- | :---: | :---: | :--- | :---: | :---: | :---: | :---: |
| **BASELINE** | 1 | **UNRESOLVED** | `UNRESOLVED_INTERNALLY` | 0 / 1 | 0 / 8 | 9,623 | 81.44s |
| **RETRY_ONLY** | 3 | **UNRESOLVED** | `UNRESOLVED_INTERNALLY` | 0 / 1 | 0 / 8 | 24,093 | 241.10s |
| **MODIFIED DDIV** | 1 | **RESOLVED** | `RESOLVED_INTERNALLY` | **1 / 1** | **8 / 8** | 15,592 | 221.80s |

### Failure Analysis of Baseline & Naive Retry:
- In **BASELINE**, the Coder identified `_query_cpu()`, but ungrounded anchor formatting caused the original patch builder to insert the block after the anchor line's leading whitespace prefix, producing a fatal `IndentationError: expected an indented block after 'if' statement on line 61`.
- In **RETRY_ONLY**, the system blindly re-prompted the Coder without supervisor diagnosis across 3 attempts, repeatedly reproducing the exact same indentation defect on every attempt.
- In **MODIFIED DDIV**, the `DemoPatchBuilder` normalized line-indexing and verified the candidate syntax with Python's AST parser, producing a clean, 1-line repair that immediately resolved the bug on Attempt 1.

---

## 4. The Verified Repair

### Candidate Patch (`results/demo_run/ddiv.patch`):
```diff
--- a/pylint/lint/run.py
+++ b/pylint/lint/run.py
@@ -58,7 +58,7 @@
             cpu_shares = int(file.read().rstrip())
         # For AWS, gives correct value * 1024.
         avail_cpu = int(cpu_shares / 1024)
-    return avail_cpu
+    return avail_cpu if avail_cpu is None or avail_cpu >= 1 else 1 
 
 
 def _cpu_count() -> int:
```

### Technical Explanation:
Under Kubernetes/Docker cgroups with fractional CPU allocations (e.g. `cpu.shares=2`), `int(2 / 1024)` truncated to `0`. Passing `processes=0` caused Python's `multiprocessing.Pool` to crash with `ValueError: Number of processes must be at least 1`.

The synthesized repair guarantees:
1. If `avail_cpu is None` (cgroups not present), it returns `None` so Pylint falls back to `multiprocessing.cpu_count()`.
2. If `avail_cpu >= 1`, it preserves the genuine container CPU limit.
3. If `avail_cpu < 1` (integer truncation to 0), it clamps the return value to `1`.

---

## 5. Exact Reproduction Instructions

### Option A: One-Command Verification from Root (Recommended)
Run the dedicated verification wrapper from `D:\DDIV`:

```powershell
python scripts/verify_demo.py
```

### Option B: Running from Workspace Directory
Because Pylint's test harness expects the target repository root to be on Python's module resolution path (`sys.path`), navigate directly into the workspace:

```powershell
cd D:\DDIV\data\workspaces\demo\eval_ws\pylint-dev__pylint-6903-eval
python -m pytest -v tests/test_pylint_runners.py
```

### Option C: Running from Root with `PYTHONPATH`
Alternatively, set `PYTHONPATH` in PowerShell:

```powershell
$env:PYTHONPATH = "D:\DDIV\data\workspaces\demo\eval_ws\pylint-dev__pylint-6903-eval"
python -m pytest -v data/workspaces/demo/eval_ws/pylint-dev__pylint-6903-eval/tests/test_pylint_runners.py
```

**Expected Test Output:**
```
============================= test session starts =============================
platform win32 -- Python 3.11.9, pytest-7.4.4, pluggy-1.6.0
rootdir: D:\PROJECTS\DDIV\data\workspaces\demo\eval_ws\pylint-dev__pylint-6903-eval
configfile: setup.cfg
plugins: anyio-4.11.0
collected 9 items

tests/test_pylint_runners.py::test_runner[run_epylint] PASSED            [ 11%]
tests/test_pylint_runners.py::test_runner[run_pylint] PASSED             [ 22%]
tests/test_pylint_runners.py::test_runner[run_pyreverse] PASSED          [ 33%]
tests/test_pylint_runners.py::test_runner[run_symilar] PASSED            [ 44%]
tests/test_pylint_runners.py::test_runner_with_arguments[run_epylint] PASSED [ 55%]
tests/test_pylint_runners.py::test_runner_with_arguments[run_pylint] PASSED [ 66%]
tests/test_pylint_runners.py::test_runner_with_arguments[run_pyreverse] PASSED [ 77%]
tests/test_pylint_runners.py::test_runner_with_arguments[run_symilar] PASSED [ 88%]
tests/test_pylint_runners.py::test_pylint_run_jobs_equal_zero_dont_crash_with_cpu_fraction PASSED [100%]

============================= 9 passed in 29.34s ==============================
```

### Step 2: Re-run the End-to-End Multi-Agent Repair
To re-run the full multi-agent repair workflow from scratch:

```powershell
python scripts/run_demo_repair.py --condition full_ddiv --output-dir results/demo_run
```

**Expected Console Output:**
```
======================================================================
 DEMO RUN COMPLETE
 Resolved:        True
 Status:          ConditionJobStatus.COMPLETED
 Attempts:        1
 Duration:        ~220s
 Patch Generated: True
 Patch Applied:   True
======================================================================
[pylint-dev__pylint-6903] Tier 1 Verdict: RESOLVED_INTERNALLY (Resolved: True)
```

---

## 6. Frozen Artifact Inventory & Integrity

All artifacts generated by this demonstration are cryptographically signed in `results/demo_freeze_manifest.json`:

| File | Purpose |
| :--- | :--- |
| `results/demo_run/ddiv.patch` | Clean candidate patch addressing the issue |
| `results/demo_run/ddiv_result.json` | Complete experiment record JSON with Tier-1 evaluation verdict |
| `results/demo_run/ddiv_model_invocations.json` | Detailed token counts, latencies, and prompts per model call |
| `results/demo_run/baseline.patch` | Baseline candidate patch showing indentation defect |
| `results/demo_run/baseline_result.json` | Baseline experiment record JSON |
| `results/demo_run/retry.patch` | Retry-only patch showing repeated failure |
| `results/demo_run/retry_result.json` | Retry-only experiment record JSON across 3 attempts |
| `results/demo_run/tier1_test_execution.log` | Verbatim pytest test execution log showing all 9 passed tests |
| `results/demo_run/token_latency_summary.json` | Comparative telemetry and token footprint summary |
| `results/demo_freeze_manifest.json` | SHA-256 integrity manifest for all demo deliverables |
