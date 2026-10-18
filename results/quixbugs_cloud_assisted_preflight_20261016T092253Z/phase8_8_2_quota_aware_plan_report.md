# DDIV Phase 8.8.2: Quota-Aware Three-Day Execution Plan & Preflight Audit

**Date:** 2026-10-16  
**Status:** Preflight Inspection Complete — Awaiting User Approval  
**Operating Mode:** Read-Only Audit & Execution Planning (Zero Model Invocations, Zero API Requests, Zero Benchmark Runs)  
**Target Benchmark Cohort:** 27 QuixBugs tasks unresolved by local `FULL_DDIV` in Phase 8.6  
**Canonical Project Root:** `D:\PROJECTS\DDIV`  
**Manifest Path:** `results\quixbugs_cloud_assisted_preflight_20261016T092253Z\unresolved_task_manifest.json`  
**Three-Day Batch Manifests:**
- JSON: `results\quixbugs_cloud_assisted_preflight_20261016T092253Z\three_day_batch_manifest.json`
- CSV: `results\quixbugs_cloud_assisted_preflight_20261016T092253Z\three_day_batch_manifest.csv`
**Dedicated Output Directory:** `results\quixbugs_cloud_assisted_repair_20261016T100000Z`  
**Isolated Memory Store:** `results\quixbugs_cloud_assisted_repair_20261016T100000Z\quixbugs_cloud_assisted_memory.db`

---

## 1. Executive Summary & Protocol Guarantees

Phase 8.8.2 establishes a quota-safe, three-day execution schedule for the 27 QuixBugs tasks that local `FULL_DDIV` failed to resolve. By partitioning the 27 challenge tasks into 3 deterministic batches of 9 tasks each, the experiment distributes cloud API consumption comfortably within daily rate and quota limits while preserving experiment identity, shared episodic memory, and methodological rigor.

### Key Preflight Findings:
1. **Zero External Calls Made:** No inference calls, API requests, network pings, or benchmark executions took place during this phase.
2. **Provider Routing Preserved (Option A Hybrid):**
   - **Locator:** Gemini `gemini-3.1-flash-lite` (Cloud)
   - **Supervisor:** Groq `qwen/qwen3.8-27b` (Cloud)
   - **Tester:** Groq `qwen/qwen3.8-27b` (Cloud)
   - **Coder:** Ollama `qwen2.5-coder:7b` (Local GPU, strictly $0.00)
3. **Automatic Fallback Violation Identified & Blocked:** `models/providers.py` (lines 237–269) contains an automatic rate-limit fallback switching between `qwen` and `gpt-oss-120b`. This unapproved model switching must be disabled to guarantee scientific reproducibility and prevent unexpected provider migration.
4. **Checkpoint/Resume Gaps Identified:** The initial runner (`scripts/run_quixbugs_cloud_assisted.py`) lacks task-skipping on existing `condition_result.json`, lacks `--batch` filtering, and aggregates tokens into a single integer without per-provider budget enforcement. Specific code modifications are documented below to resolve these blockers before execution.
5. **Episodic Memory Continuity Confirmed:** The multi-day batch design operates against a single unified output directory and database (`quixbugs_cloud_assisted_memory.db`), ensuring learned negative constraints and failure diagnoses persist across Day 1, Day 2, and Day 3 without reset.

---

## 2. Three-Day Deterministic Batch Partitioning

The 27 unresolved tasks are divided into three 9-task batches strictly preserving the canonical manifest sequence:

| Batch ID | Execution Day | Tasks | Phase 8.6 Failure Profile | Est. Gemini Tokens | Est. Groq Tokens (Max) | Est. Ollama Tokens (Max) |
| :--- | :---: | :---: | :--- | :---: | :---: | :---: |
| **`batch_1`** | **Day 1** | 9 | 1 TIMEOUT, 8 ASSERTION_FAILURE | ~14,850 | ~93,150 | ~60,750 |
| **`batch_2`** | **Day 2** | 9 | 6 ASSERTION_FAILURE, 2 SYNTAX, 1 ANCHOR | ~14,850 | ~93,150 | ~60,750 |
| **`batch_3`** | **Day 3** | 9 | 4 ASSERTION, 1 TIMEOUT, 2 SYNTAX, 1 ANCHOR, 1 REVISION | ~14,850 | ~93,150 | ~60,750 |
| **Total Cohort** | **3 Days** | **27** | **18 Assertion, 2 Timeout, 4 Syntax, 2 Anchor, 1 Revision** | **~44,550** | **~279,450** | **~182,250** |

### Detailed Batch Allocations:

#### Batch 1 (Day 1: Tasks 1–9)
1. `quixbugs-python-bitcount` (`bitcount.py`) — Prior: TIMEOUT (5,362 local tokens, 57.1s)
2. `quixbugs-python-depth_first_search` (`depth_first_search.py`) — Prior: ASSERTION_FAILURE (6,458 local tokens, 37.7s)
3. `quixbugs-python-detect_cycle` (`detect_cycle.py`) — Prior: ASSERTION_FAILURE (6,254 local tokens, 38.7s)
4. `quixbugs-python-find_in_sorted` (`find_in_sorted.py`) — Prior: ASSERTION_FAILURE (5,461 local tokens, 32.2s)
5. `quixbugs-python-gcd` (`gcd.py`) — Prior: ASSERTION_FAILURE (8,547 local tokens, 48.9s)
6. `quixbugs-python-get_factors` (`get_factors.py`) — Prior: ASSERTION_FAILURE (8,152 local tokens, 39.2s)
7. `quixbugs-python-hanoi` (`hanoi.py`) — Prior: ASSERTION_FAILURE (8,346 local tokens, 50.5s)
8. `quixbugs-python-kheapsort` (`kheapsort.py`) — Prior: ASSERTION_FAILURE (7,364 local tokens, 37.7s)
9. `quixbugs-python-knapsack` (`knapsack.py`) — Prior: ASSERTION_FAILURE (8,611 local tokens, 45.1s)

#### Batch 2 (Day 2: Tasks 10–18)
10. `quixbugs-python-lcs_length` (`lcs_length.py`) — Prior: ASSERTION_FAILURE (9,405 local tokens, 41.1s)
11. `quixbugs-python-lis` (`lis.py`) — Prior: ASSERTION_FAILURE (8,054 local tokens, 42.1s)
12. `quixbugs-python-longest_common_subsequence` (`longest_common_subsequence.py`) — Prior: ASSERTION_FAILURE (7,086 local tokens, 37.8s)
13. `quixbugs-python-mergesort` (`mergesort.py`) — Prior: SYNTAX_ERROR_INDENTATION (5,373 local tokens, 25.9s)
14. `quixbugs-python-minimum_spanning_tree` (`minimum_spanning_tree.py`) — Prior: ANCHOR_NOT_FOUND (7,200 local tokens, 37.3s)
15. `quixbugs-python-next_palindrome` (`next_palindrome.py`) — Prior: ASSERTION_FAILURE (6,117 local tokens, 25.9s)
16. `quixbugs-python-next_permutation` (`next_permutation.py`) — Prior: ASSERTION_FAILURE (7,917 local tokens, 30.2s)
17. `quixbugs-python-possible_change` (`possible_change.py`) — Prior: SYNTAX_ERROR_INDENTATION (6,736 local tokens, 52.0s)
18. `quixbugs-python-powerset` (`powerset.py`) — Prior: ASSERTION_FAILURE (6,838 local tokens, 28.5s)

#### Batch 3 (Day 3: Tasks 19–27)
19. `quixbugs-python-shortest_path_length` (`shortest_path_length.py`) — Prior: ASSERTION_FAILURE (7,248 local tokens, 32.4s)
20. `quixbugs-python-shortest_path_lengths` (`shortest_path_lengths.py`) — Prior: ASSERTION_FAILURE (7,177 local tokens, 37.2s)
21. `quixbugs-python-shortest_paths` (`shortest_paths.py`) — Prior: ANCHOR_NOT_FOUND (5,962 local tokens, 23.2s)
22. `quixbugs-python-shunting_yard` (`shunting_yard.py`) — Prior: ASSERTION_FAILURE (7,526 local tokens, 33.4s)
23. `quixbugs-python-sieve` (`sieve.py`) — Prior: ASSERTION_FAILURE (6,965 local tokens, 35.4s)
24. `quixbugs-python-sqrt` (`sqrt.py`) — Prior: TIMEOUT (5,871 local tokens, 70.5s)
25. `quixbugs-python-subsequences` (`subsequences.py`) — Prior: PATCH_APPLICATION_FAILED (6,522 local tokens, 60.8s)
26. `quixbugs-python-topological_ordering` (`topological_ordering.py`) — Prior: SYNTAX_ERROR_INDENTATION (6,448 local tokens, 47.7s)
27. `quixbugs-python-wrap` (`wrap.py`) — Prior: PATCH_REVISION_MISMATCH (5,618 local tokens, 27.9s)

---

## 3. Token Accounting, Quota Limits & Provider Audit

### 3.1 Verification of Free-Tier Limits
- **Account-Specific Rate Limit Audit:** Account-specific remaining token balances and daily quotas **cannot be queried programmatically via read-only inspection** without initiating authenticated API completions.
- **Published Standard Free-Tier Ceilings:**
  - **Google Gemini (Developer Free Tier):**
    - Rate Limit: 15 Requests Per Minute (RPM)
    - Throughput Limit: 1,000,000 Tokens Per Minute (TPM)
    - Daily Quota: 1,500 Requests Per Day (RPD)
    - Financial Cost: **$0.00**
  - **Groq Cloud (Developer Free Tier):**
    - Rate Limit: 30 Requests Per Minute (RPM)
    - Throughput Limit: **6,000 Tokens Per Minute (TPM)** (Strict bottleneck)
    - Daily Quota: 14,400 Requests Per Day (RPD)
    - Financial Cost: **$0.00**
  - **Local Ollama:**
    - Unlimited RPM / TPM / RPD (Bound only by local GPU memory and thermals)
    - Financial Cost: **$0.00**

### 3.2 Throughput Bottleneck Mitigation (The 6,000 Groq TPM Ceiling)
In a multi-agent loop, a single repair attempt generates:
- Supervisor diagnosis: ~2,400 tokens
- Tester critique: ~1,850 tokens
- Combined Groq throughput: **~4,250 tokens in ~3–5 seconds**

If tasks execute without inter-attempt pacing, two consecutive attempts would exceed Groq's 6,000 TPM limit and trigger HTTP 429 rate limit errors.
**Mitigation:** The runner must incorporate a mandatory **10-second pacing delay** between consecutive Groq calls and a **15-second delay** between tasks.

### 3.3 Conservative Daily Token Budgets & Safety Margins

| Provider | Expected Mean Daily Tokens | Hard Daily Budget Ceiling | Margin of Safety |
| :--- | :---: | :---: | :---: |
| **Groq (Supervisor + Tester)** | ~55,000 – ~65,000 | **100,000 tokens** | **+54% over expected** |
| **Gemini (Locator)** | ~14,850 | **30,000 tokens** | **+102% over expected** |
| **Ollama (Coder)** | ~40,000 – ~60,000 | Unlimited (Local) | N/A |

If the daily token consumption for Groq approaches or reaches 100,000 tokens, the runner must halt immediately, finalize the partial batch results, and preserve all checkpoints.

---

## 4. Checkpoint, Resume & Provider Behavior Audit

### 4.1 Audit of Existing Runner (`scripts/run_quixbugs_cloud_assisted.py`)

| Feature Requirement | Current Implementation Status | Evaluation | Required Action |
| :--- | :---: | :---: | :--- |
| **Checkpoint Detection** | Missing | **BLOCKER** | If `(output_dir / prog_name / "condition_result.json").exists()`, skip execution and load existing result. |
| **Batch Selection CLI** | Missing | **BLOCKER** | Add `--batch {1,2,3}` and `--batch-manifest` arguments to filter target tasks. |
| **Per-Provider Token Tracking** | Incomplete (Aggregated into single integer) | **BLOCKER** | Record tokens separately for Gemini, Groq (Supervisor), Groq (Tester), and Ollama. |
| **Daily Budget Guard** | Missing | **BLOCKER** | Add `--max-daily-groq-tokens` and `--max-daily-gemini-tokens` with graceful stop. |
| **Pacing / Rate Limiting** | Missing (Runs in tight loop) | **WARNING** | Add `--request-delay` (10s) between Groq requests to prevent 6,000 TPM exhaustion. |
| **Model Fallback Prevention** | `models/providers.py:237-269` contains active fallback | **BLOCKER** | Pass explicit flag `disable_fallback=True` to prevent automatic fallback to `gpt-oss-120b`. |
| **Episodic Memory Isolation** | Preserved (`quixbugs_cloud_assisted_memory.db`) | **COMPLIANT** | Reuses same SQLite DB across batches without resetting. |
| **Ground Truth Isolation** | Strict (only target file in workspace) | **COMPLIANT** | Zero tests or gold patches exposed to any agent. |

---

## 5. Required Code Enhancements (Patch Specification)

The following changes are required in `scripts/run_quixbugs_cloud_assisted.py` prior to authorized execution:

### 5.1 Checkpoint / Resumption Logic
```python
# In QuixBugsCloudAssistedRunner.run_all():
for i, t_info in enumerate(self.manifest_tasks, 1):
    t_id = t_info["canonical_task_id"]
    p_name = t_info["program_name"]
    result_file = self.output_dir / p_name / "condition_result.json"

    # Checkpoint Check
    if result_file.exists():
        try:
            cached_res = json.loads(result_file.read_text(encoding="utf-8"))
            if cached_res.get("condition") == "CLOUD_ASSISTED_DDIV":
                print(f"  [CHECKPOINT] Task {p_name} already completed. Resuming from disk...")
                all_results[p_name] = cached_res
                if cached_res.get("resolved"):
                    resolved_count += 1
                continue
        except Exception as e:
            print(f"  [CHECKPOINT WARNING] Corrupt result for {p_name}: {e}. Re-running...")
```

### 5.2 Daily Quota Safety Ceiling
```python
# Before each task or attempt:
if self.daily_groq_tokens >= self.max_daily_groq_tokens:
    print(f"\n[QUOTA GUARD] Daily Groq token budget reached ({self.daily_groq_tokens} >= {self.max_daily_groq_tokens}).")
    print(f"[QUOTA GUARD] Halting execution cleanly. Progress preserved for next batch.")
    break
```

### 5.3 Batch Selection CLI Arguments
```python
parser.add_argument("--batch", type=int, choices=[1, 2, 3], help="Specific batch to execute (1, 2, or 3)")
parser.add_argument("--batch-manifest", type=str, default="results/quixbugs_cloud_assisted_preflight_20261016T092253Z/three_day_batch_manifest.json")
parser.add_argument("--max-daily-groq-tokens", type=int, default=100000, help="Daily ceiling for Groq tokens")
parser.add_argument("--max-daily-gemini-tokens", type=int, default=30000, help="Daily ceiling for Gemini tokens")
parser.add_argument("--pacing-delay", type=float, default=10.0, help="Seconds to sleep between cloud requests to honor TPM limits")
```

---

## 6. Execution Protocol & Exact Commands

When authorized, the three-day experiment will be executed using the following sequential PowerShell commands from working directory `D:\PROJECTS\DDIV`:

### Day 1 Execution (Batch 1: Tasks 1–9)
```powershell
Set-Location -Path "D:\PROJECTS\DDIV"
python scripts/run_quixbugs_cloud_assisted.py `
  --task-manifest "results/quixbugs_cloud_assisted_preflight_20261016T092253Z/unresolved_task_manifest.json" `
  --batch-manifest "results/quixbugs_cloud_assisted_preflight_20261016T092253Z/three_day_batch_manifest.json" `
  --batch 1 `
  --output-dir "results/quixbugs_cloud_assisted_repair_20261016T100000Z" `
  --max-attempts 3 `
  --coder-provider ollama `
  --max-daily-groq-tokens 100000 `
  --max-daily-gemini-tokens 30000 `
  --pacing-delay 10.0
```

### Day 2 Execution (Batch 2: Tasks 10–18)
```powershell
Set-Location -Path "D:\PROJECTS\DDIV"
python scripts/run_quixbugs_cloud_assisted.py `
  --task-manifest "results/quixbugs_cloud_assisted_preflight_20261016T092253Z/unresolved_task_manifest.json" `
  --batch-manifest "results/quixbugs_cloud_assisted_preflight_20261016T092253Z/three_day_batch_manifest.json" `
  --batch 2 `
  --output-dir "results/quixbugs_cloud_assisted_repair_20261016T100000Z" `
  --max-attempts 3 `
  --coder-provider ollama `
  --max-daily-groq-tokens 100000 `
  --max-daily-gemini-tokens 30000 `
  --pacing-delay 10.0
```

### Day 3 Execution (Batch 3: Tasks 19–27)
```powershell
Set-Location -Path "D:\PROJECTS\DDIV"
python scripts/run_quixbugs_cloud_assisted.py `
  --task-manifest "results/quixbugs_cloud_assisted_preflight_20261016T092253Z/unresolved_task_manifest.json" `
  --batch-manifest "results/quixbugs_cloud_assisted_preflight_20261016T092253Z/three_day_batch_manifest.json" `
  --batch 3 `
  --output-dir "results/quixbugs_cloud_assisted_repair_20261016T100000Z" `
  --max-attempts 3 `
  --coder-provider ollama `
  --max-daily-groq-tokens 100000 `
  --max-daily-gemini-tokens 30000 `
  --pacing-delay 10.0
```

### Safe Resumption Command (If Halted by Quota Ceiling)
```powershell
# Re-running the same command automatically skips already completed tasks:
python scripts/run_quixbugs_cloud_assisted.py `
  --batch 1 `
  --output-dir "results/quixbugs_cloud_assisted_repair_20261016T100000Z"
```

---

## 7. Preflight Gate Affirmation

1. **Zero External Calls Made:** Confirmed. No API calls or benchmark invocations occurred during this phase.
2. **Read-Only Status Preserved:** Existing Phase 8.6 benchmark data and production database `data/ddiv_memory.db` remain untouched.
3. **Execution Blocked:** Execution is paused. The system will NOT launch the benchmark or invoke remote models until explicit user authorization is provided.
