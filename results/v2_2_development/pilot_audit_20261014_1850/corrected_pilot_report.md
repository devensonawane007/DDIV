# DDIV v2.2 Corrected Five-Task Pilot Report

> [!NOTE]
> **Evaluation Framework Scope & Methodology:**
> All evaluations reported herein are **Tier-1 Internal Reproductions** using SWE-bench Verified dataset specifications,
> exact target FAIL_TO_PASS test execution, and PASS_TO_PASS regression suites in isolated repository environments.
> **These are internal controlled experimental metrics under DDIV and DO NOT represent official SWE-bench evaluation harness submissions.**
> Official SWE-bench evaluation was not executed for this pilot.

---

## 1. Executive Summary & Verification

- **Total Planned Runs:** 15 (5 tasks × 3 conditions: `BASELINE`, `RETRY_ONLY`, `FULL_DDIV`)
- **Total Completed Runs:** 15/15 (100% accounted for)
- **Archived Infrastructure Interruption Records:** 2 (Ollama daemon restart during Task 4, preserved in `infrastructure_aborts/`)
- **Coder Model (Treatment):** `qwen2.5-coder:7b` via local Ollama (`http://localhost:11434`)
- **Zero Cloud Fallback Guarantee:** 100% verified — zero cloud fallback calls for Coder across all runs
- **Supporting Agents:** `gemini-3.1-flash-lite` (Locator), `qwen/qwen3.8-27b` via Groq (Supervisor, RCA, Critic, Tester)
- **Tier-1 Internal Resolved Count:** 0/15 (0.0% resolution across all conditions)

---

## 2. Condition Comparison Summary

| Condition | Completed / Planned | Patch Gen (Any Att) | Final Patch Applied | Tests Actually Executed | Tier-1 Resolved | Pass@1 Count | Avg Tokens | Avg Wall-Clock (s) | Total Wall-Clock |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **BASELINE** | 5/5 | 1/5 | 1/5 | 1/5 tasks | 0/5 (0.0%) | 0 | 8,928.6 | 131.9s | 659.3s |
| **RETRY_ONLY** | 5/5 | 3/5 | 3/5 | 3/5 tasks | 0/5 (0.0%) | 0 | 26,818.0 | 294.2s | 1470.9s |
| **FULL_DDIV** | 5/5 | 5/5 | 0/5 | 0/5 tasks | 0/5 (0.0%) | 0 | 41,454.6 | 323.9s | 1619.3s |

---

## 3. Disentangled Per-Run Evaluation Matrix

To resolve prior denominator ambiguities, test metrics are explicitly separated into **Ground Truth Total in Dataset** vs. **Tests Actually Executed by Evaluator**. Tests not run due to patch application failure are marked as `Not Run (Apply Failed)`.

| Task ID | Condition | Status | Attempts | Final Patch Applied | F2P Tested / GT | F2P Passed | P2P Tested / GT | P2P Passed | Tier-1 Resolved | Total Tokens | Duration | Verified Primary Failure Cause |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| `pylint-6903` | `BASELINE` | COMPLETED | 1 | Yes | 1 / 1 | 0 | 8 / 8 | 8 | ❌ NO | 9,633 | 157.3s | `PATCH_LOGIC_INCORRECT` (F2P failed) |
| `pylint-6903` | `RETRY_ONLY` | COMPLETED | 3 | Yes | 1 / 1 | 0 | 8 / 8 | 8 | ❌ NO | 29,317 | 342.6s | `PATCH_LOGIC_INCORRECT` (F2P failed) |
| `pylint-6903` | `FULL_DDIV` | COMPLETED | 3 | No | 0 / 1 | Not Run | 0 / 8 | Not Run | ❌ NO | 46,706 | 313.5s | `PATCH_APPLICATION_FAILED` (git apply failed) |
| `seaborn-3187` | `BASELINE` | COMPLETED | 1 | No | 0 / 2 | Not Run | 0 / 248 | Not Run | ❌ NO | 9,209 | 161.2s | `PATCH_BUILDER_FAILED` (Anchor not found) |
| `seaborn-3187` | `RETRY_ONLY` | COMPLETED | 3 | No | 0 / 2 | Not Run | 0 / 248 | Not Run | ❌ NO | 27,819 | 182.0s | `PATCH_BUILDER_FAILED` (Anchor not found) |
| `seaborn-3187` | `FULL_DDIV` | COMPLETED | 3 | No | 0 / 2 | Not Run | 0 / 248 | Not Run | ❌ NO | 41,531 | 370.6s | `PATCH_BUILDER_FAILED` (Anchor not found) |
| `xarray-7393` | `BASELINE` | COMPLETED | 1 | No | 0 / 2 | Not Run | 0 / 71 | Not Run | ❌ NO | 10,127 | 155.8s | `PATCH_BUILDER_FAILED` (Ambiguous anchor) |
| `xarray-7393` | `RETRY_ONLY` | COMPLETED | 3 | Yes | 2 / 2 | 0 | 10 / 71* | 0 | ❌ NO | 30,896 | 265.9s | `PATCH_LOGIC_INCORRECT` (F2P failed, P2P regressed) |
| `xarray-7393` | `FULL_DDIV` | COMPLETED | 3 | No | 0 / 2 | Not Run | 0 / 71 | Not Run | ❌ NO | 44,932 | 240.7s | `PATCH_APPLICATION_FAILED` (git apply failed) |
| `astropy-8872` | `BASELINE` | COMPLETED | 1 | No | 0 / 1 | Not Run | 0 / 80 | Not Run | ❌ NO | 9,524 | 102.3s | `PATCH_BUILDER_FAILED` (Phantom file path) |
| `astropy-8872` | `RETRY_ONLY` | COMPLETED | 3 | No | 0 / 1 | Not Run | 0 / 80 | Not Run | ❌ NO | 28,628 | 421.2s | `PATCH_BUILDER_FAILED` (Anchor not found) |
| `astropy-8872` | `FULL_DDIV` | COMPLETED | 3 | No (Att 3) | 0 / 1 | Not Run | 0 / 80 | Not Run | ❌ NO | 34,981 | 418.2s | `PATCH_BUILDER_FAILED` (Anchor not found in Att 3) |
| `requests-2931` | `BASELINE` | COMPLETED | 1 | No | 0 / 1 | Not Run | 0 / 84 | Not Run | ❌ NO | 6,150 | 82.7s | `PATCH_BUILDER_FAILED` (AST syntax error) |
| `requests-2931` | `RETRY_ONLY` | COMPLETED | 3 | Yes | 1 / 1 | 0 | 10 / 84* | 0 | ❌ NO | 17,430 | 259.3s | `PATCH_LOGIC_INCORRECT` (F2P failed, P2P regressed) |
| `requests-2931` | `FULL_DDIV` | COMPLETED | 3 | No | 0 / 1 | Not Run | 0 / 84 | Not Run | ❌ NO | 39,123 | 276.3s | `PATCH_APPLICATION_FAILED` (git apply failed) |

*\*Note on P2P subset:* The Tier-1 evaluator executes a maximum of `max_p2p_tests=10` regression tests to avoid execution timeouts. For runs where the patch applied (`xarray-7393` and `requests-2931` in `RETRY_ONLY`), 10 P2P tests were executed. For unapplied patches, zero tests were executed.

---

## 4. Infrastructure Interruptions (Archived Separately)

| Task ID | Condition | Status | Timestamp | Cause | Evidence File |
| :--- | :---: | :---: | :---: | :--- | :--- |
| `astropy-8872` | `RETRY_ONLY` | ABORTED | 2026-10-14 18:04 | Local Ollama daemon terminated during host reboot | `aborted_astropy__astropy-8872__retry_only.json` |
| `astropy-8872` | `FULL_DDIV` | ABORTED | 2026-10-14 18:07 | Local Ollama daemon terminated during host reboot | `aborted_astropy__astropy-8872__full_ddiv.json` |

Both runs were restarted and executed to completion once Ollama was verified online. These aborted events are excluded from repair performance metrics.

---

## 5. Corrected Audit Findings
1. **Zero Resolution Across All Conditions:** None of the 15 runs achieved resolution under Tier-1 internal evaluation.
2. **Patch Application Rates:**
   - `BASELINE`: 1/5 patches applied (20.0%)
   - `RETRY_ONLY`: 3/5 patches applied (60.0%)
   - `FULL_DDIV`: 0/5 final patches applied (0.0% on final attempt; 1/5 on Attempt 1)
3. **Core Failure Root Cause:** The local `qwen2.5-coder:7b` model suffers from severe **anchor hallucination**—generating altered whitespace, parameter types, or function signatures from pre-training memory rather than extracting verbatim anchors from repository context.
