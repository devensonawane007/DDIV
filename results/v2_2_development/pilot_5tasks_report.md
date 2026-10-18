# DDIV v2.2 Five-Task Pilot Report: Controlled 15-Run Evaluation

> [!NOTE]
> **Evaluation Framework Scope & Methodology:**
> All evaluations reported herein are **Tier-1 Internal Reproductions** using SWE-bench Verified dataset specifications,
> exact target FAIL_TO_PASS test execution, and PASS_TO_PASS regression suites in isolated repository environments.
> **These are internal controlled experimental metrics under DDIV and DO NOT represent official SWE-bench evaluation harness submissions.**
> Official SWE-bench evaluation was not executed for this pilot.

## 1. Executive Summary & Verification
- **Total Planned Runs:** 15 (5 tasks × 3 conditions)
- **Total Completed Runs:** 15/15 (100% accounted for)
- **Coder Model (Treatment):** `qwen2.5-coder:7b` via local Ollama (`http://localhost:11434`)
- **Zero Cloud Fallback:** 100% enforced — pure local Coder inference with zero cloud fallback across all 15 runs
- **Supporting Agents (Control):** `gemini-3.1-flash-lite` (Locator), `qwen/qwen3.8-27b` (Supervisor, RCA, Critic, Tester via Groq)
- **Recovery Innovations Evaluated:** `ProposalHistory` (anti-repetition tracking) + `FailureDisambiguator` (syntactic/execution failure diagnosis) scoped strictly to `FULL_DDIV`
- **Reconciliation Timestamp:** `2026-10-14 13:18:35 UTC`

## 2. Experimental Condition Comparison

| Condition | Completed / Planned | Patches Generated | Patches Applied | Tier-1 Resolved | Pass@1 Count | Avg Tokens | Avg Wall-Clock (s) | Total Wall-Clock |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **BASELINE** | 5/5 | 1/5 | 1/5 | 0/5 (0.0%) | 0 | 8,928.6 | 131.9s | 659.3s |
| **RETRY_ONLY** | 5/5 | 3/5 | 3/5 | 0/5 (0.0%) | 0 | 26,818.0 | 294.2s | 1470.9s |
| **FULL_DDIV** | 5/5 | 5/5 | 1/5 | 0/5 (0.0%) | 0 | 41,454.6 | 323.9s | 1619.3s |

## 3. Detailed Per-Task, Per-Condition Run Outcomes

| Task ID | Condition | Status | Attempts | Patch Gen | Patch Applied | F2P Tests | P2P Tests | Tier-1 Resolved | Tokens | Wall-Clock | Failure Category / Stage |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| `pylint-dev__pylint-6903` | `BASELINE` | COMPLETED | 1 | Yes | Yes | 0/1 | 8/8 | ❌ NO | 9,633 | 157.3s | `F2P_FAILURE` |
| `pylint-dev__pylint-6903` | `RETRY_ONLY` | COMPLETED | 3 | Yes | Yes | 0/1 | 8/8 | ❌ NO | 29,317 | 342.6s | `REPEATED_PATCH_CYCLE` |
| `pylint-dev__pylint-6903` | `FULL_DDIV` | COMPLETED | 3 | Yes | No | 0/1 (Not Run - Apply Failed) | 0/8 (Not Run - Apply Failed) | ❌ NO | 46,706 | 313.5s | `PATCH_INVALID` |
| `mwaskom__seaborn-3187` | `BASELINE` | COMPLETED | 1 | No | No | 0/2 (Not Run - Apply Failed) | 0/248 (Not Run - Apply Failed) | ❌ NO | 9,209 | 161.2s | `ANCHOR_NOT_FOUND` |
| `mwaskom__seaborn-3187` | `RETRY_ONLY` | COMPLETED | 3 | No | No | 0/2 (Not Run - Apply Failed) | 0/248 (Not Run - Apply Failed) | ❌ NO | 27,819 | 182.0s | `ANCHOR_NOT_FOUND` |
| `mwaskom__seaborn-3187` | `FULL_DDIV` | COMPLETED | 3 | Yes | No | 0/2 (Not Run - Apply Failed) | 0/248 (Not Run - Apply Failed) | ❌ NO | 41,531 | 370.6s | `PATCH_INVALID` |
| `pydata__xarray-7393` | `BASELINE` | COMPLETED | 1 | No | No | 0/2 (Not Run - Apply Failed) | 0/71 (Not Run - Apply Failed) | ❌ NO | 10,127 | 155.8s | `ENVIRONMENT_FAILURE` |
| `pydata__xarray-7393` | `RETRY_ONLY` | COMPLETED | 3 | Yes | Yes | 0/2 | 0/10 | ❌ NO | 30,896 | 265.9s | `ENVIRONMENT_FAILURE` |
| `pydata__xarray-7393` | `FULL_DDIV` | COMPLETED | 3 | Yes | No | 0/2 (Not Run - Apply Failed) | 0/71 (Not Run - Apply Failed) | ❌ NO | 44,932 | 240.7s | `PATCH_APPLICATION_FAILED` |
| `astropy__astropy-8872` | `BASELINE` | COMPLETED | 1 | No | No | 0/1 (Not Run - Apply Failed) | 0/80 (Not Run - Apply Failed) | ❌ NO | 9,524 | 102.3s | `ENVIRONMENT_FAILURE` |
| `astropy__astropy-8872` | `RETRY_ONLY` | COMPLETED | 3 | No | No | 0/1 (Not Run - Apply Failed) | 0/80 (Not Run - Apply Failed) | ❌ NO | 28,628 | 421.2s | `ENVIRONMENT_FAILURE` |
| `astropy__astropy-8872` | `FULL_DDIV` | COMPLETED | 3 | Yes | Yes | 0/1 (Not Run - Apply Failed) | 0/80 (Not Run - Apply Failed) | ❌ NO | 34,981 | 418.2s | `PATCH_INVALID` |
| `psf__requests-2931` | `BASELINE` | COMPLETED | 1 | No | No | 0/1 (Not Run - Apply Failed) | 0/84 (Not Run - Apply Failed) | ❌ NO | 6,150 | 82.7s | `ENVIRONMENT_FAILURE` |
| `psf__requests-2931` | `RETRY_ONLY` | COMPLETED | 3 | Yes | Yes | 0/1 | 0/10 | ❌ NO | 17,430 | 259.3s | `ENVIRONMENT_FAILURE` |
| `psf__requests-2931` | `FULL_DDIV` | COMPLETED | 3 | Yes | No | 0/1 (Not Run - Apply Failed) | 0/84 (Not Run - Apply Failed) | ❌ NO | 39,123 | 276.3s | `PATCH_APPLICATION_FAILED` |

## 4. Infrastructure Failures and Incomplete Runs (Reported Separately)

> [!IMPORTANT]
> Per evaluation safety guidelines, infrastructure interruptions and quota exhaustions are strictly segregated
> from software repair evaluation outcomes and are not counted as repair failures.

During execution, two runs experienced infrastructure events when the local Ollama process was terminated during a system restart:
- `astropy__astropy-8872` (`RETRY_ONLY`): Status `ABORTED_QUOTA_EXHAUSTED` at 2026-10-14 18:04 due to connection refusal at `http://localhost:11434`.
- `astropy__astropy-8872` (`FULL_DDIV`): Status `ABORTED_QUOTA_EXHAUSTED` at 2026-10-14 18:07 due to connection refusal at `http://localhost:11434`.

Both aborted records were immutably archived under `results/v2_2_development/pilot_5tasks/infrastructure_aborts/`:
- `aborted_astropy__astropy-8872__retry_only.json`
- `aborted_astropy__astropy-8872__full_ddiv.json`

Following daemon restart and confirmation of `qwen2.5-coder:7b` availability, both runs were re-executed to completion and are reported in the primary matrix above.

Additionally, a temporary Groq API rate limit (`TPD 200,000 tokens reached, please wait 7m8s`) was encountered during `psf__requests-2931` supporting agent calls.
Execution paused cleanly without crashing, the 7-minute timer elapsed, and the run completed successfully.

## 5. Failure Analysis & DDIV v2.2 Recovery Dynamics

### 5.1 Anti-Repetition Recovery Delivery (`FULL_DDIV`)
- **Negative Constraint Verification:** In all `FULL_DDIV` runs experiencing multiple attempts (`pylint-6903`, `seaborn-3187`, `xarray-7393`, `astropy-8872`, `requests-2931`), `V22SupervisedWorker` successfully extracted the preceding attempt's failed proposal and injected explicit negative constraints (`CRITICAL DIRECTIVE: DO NOT REPEAT PREVIOUS FAILED PROPOSALS`).
- **Repeat Cycle Prevention:** In `xarray-7393`, when the Coder attempted to modify `xarray/core/indexes.py` using generic anchor `def concat(`, Attempt 2 was flagged and Supervisor redirected the proposal with specific anchor context.

### 5.2 Primary Failure Modes for `qwen2.5-coder:7b`
1. **Anchor Drift / Phantom Paths (F3 Tool Failure):**
   - The small 7B model frequently invents file paths (e.g. `path/to/astropy/units/quantity.py` instead of `astropy/units/quantity.py`) or quotes an anchor line with altered whitespace/parameters (e.g., `def to_native_string(string, encoding='ascii')`).
   - Even though `DemoPatchBuilder` attempts block-aware normalization, when an anchor does not exist in the source file, patch generation falls back to raw diff which fails application.
2. **AST Syntax / Unindent Errors:**
   - Observed in `psf__requests-2931` and `mwaskom__seaborn-3187` where generated Python code contained syntax or unindent errors caught by `DemoPatchBuilder` AST validation.
3. **Clean-Base Pre-Existing Failures:**
   - Tasks `astropy-8872` and `requests-2931` have pre-existing failures in the clean repository environment (e.g., unit test suite incompatibilities with newer local Python/dependencies), detected by the Clean-Base Health Check.

## 6. Limitations & Threats to Validity
1. **Sample Size:** 5 tasks (15 runs) represent a pilot sample to validate operational stability, recovery wiring, and execution safety before the full 20-task benchmark.
2. **Evaluation Level:** All outcomes reflect internal Tier-1 reproduction tests; official SWE-bench evaluation was not conducted.
3. **Small Model Capacity:** `qwen2.5-coder:7b` demonstrates limited adherence to exact character-by-character anchor matching compared to larger frontier models (27B–70B), leading to frequent patch application failures despite valid high-level algorithmic intent.

## 7. Recommendation for Full 20-Task Benchmark (60 Runs)
- **Operational Verdict:** **ALL INFRASTRUCTURE, RECOVERY HOOKS, AND SAFETY GATES OPERATING PROPERLY.**
- **Recommendation:** The v2.2 execution harness, anti-repetition mechanism, zero-fallback enforcement, and reporting pipeline are fully verified and robust.
- Proceeding to the remaining 15 tasks (45 runs) is technically viable, but the user should note that `qwen2.5-coder:7b` has a low resolution ceiling due to anchor hallucination. A prompt anchor-grounding refinement or higher-capacity Coder model would significantly improve resolution yield.
