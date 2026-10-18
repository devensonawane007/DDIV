# DDIV Phase 8.8: Reconciliation Audit of Phase 8.7 Benchmark Metrics

## 1. Executive Summary: Investigation of Numerical Inconsistencies

A forensic re-audit of all 40 canonical QuixBugs task directories in `results/quixbugs_benchmark_40tasks_20261016T125500Z` was conducted to reconcile the exact attempt counts and metric discrepancies observed in Phase 8.7 documentation.

### The Specific Discrepancy Investigated
The Phase 8.7 analytical report stated:
- 13 `FULL_DDIV` tasks resolved (8 on Attempt 1, 4 on Attempt 2, 1 on Attempt 3).
- 27 `FULL_DDIV` tasks unresolved.
- 96 `FULL_DDIV` attempts total (mean 2.40 attempts/task).

### Mathematical Conflict Identified
If all 27 unresolved tasks had exhausted the 3-attempt budget:
$$\text{Unresolved Attempts} = 27 \times 3 = 81$$
$$\text{Resolved Attempts} = (8 \times 1) + (4 \times 2) + (1 \times 3) = 8 + 8 + 3 = 19$$
$$\text{Total True Attempts} = 19 + 81 = \mathbf{100 \text{ attempts (mean } 2.50 \text{ attempts/task)}}$$

A total of 96 attempts would only be possible if 4 attempts had been truncated across the 27 unresolved tasks (e.g., 2 unresolved tasks stopping early at Attempt 1, or 4 stopping at Attempt 2).

---

## 2. Empirical Findings from Underlying JSON Result Files

Each individual `condition_result.json` was examined directly:

1. **Attempt Exhaustion Across Unresolved Tasks:**
   - **All 27 unresolved tasks executed exactly 3 attempts.**
   - Zero unresolved tasks experienced early termination or premature aborts.
   - Every unresolved task record contains exactly 3 attempt entries in its `history` array.
   - Sum of attempts across unresolved tasks = **81 attempts**.

2. **Attempts Across Resolved Tasks:**
   - 8 tasks resolved on Attempt 1 and stopped early (8 attempts).
   - 4 tasks resolved on Attempt 2 and stopped early (8 attempts).
   - 1 task resolved on Attempt 3 (3 attempts).
   - Sum of attempts across resolved tasks = **19 attempts**.

3. **True Aggregate Total:**
   $$\text{Total True FULL\_DDIV Attempts} = 19 + 81 = \mathbf{100}$$
   $$\text{True Mean Attempts per Task} = \frac{100}{40} = \mathbf{2.50}$$

4. **Origin of the '96' Discrepancy:**
   - In `results/quixbugs_baseline_vs_fullddiv_audit_20261016T083103Z/aggregate_metrics_comparison.csv`, the recorded value was **already 100 attempts** (mean 2.50).
   - However, in `scripts/run_phase8_7_analysis.py`, several markdown reporting strings contained a hardcoded draft string `"96"` carried over from an early dry-run iteration.
   - This typographical discrepancy in the markdown text is now conclusively resolved: **the true empirical value is 100 attempts**.

---

## 3. Reconciled Baseline vs FULL_DDIV Benchmark Metrics

| Metric Dimension | Reconciled BASELINE | Reconciled FULL_DDIV | Verified Delta | Verification Method |
| :--- | :---: | :---: | :---: | :--- |
| **Tasks Evaluated** | 40 | 40 | 0 | 40 canonical QuixBugs directories |
| **Tasks Resolved** | **8 / 40 (20.0%)** | **13 / 40 (32.5%)** | **+5 (+62.5% rel)** | 100% specification tests pass |
| **Tasks Unresolved** | 32 / 40 (80.0%) | 27 / 40 (67.5%) | -5 (-15.6%) | Exhausted attempt budget |
| **Total Attempts** | **40** | **100** | **+60 (+150%)** | Sum of attempts across 40 tasks |
| **Mean Attempts / Task** | **1.00** | **2.50** | **+1.50** | Attempts / 40 tasks |
| **Resolved on Attempt 1** | 8 | 8 | 0 | One-shot solvable in both |
| **Resolved on Attempt 2** | 0 | 4 | +4 | Multi-attempt recovery |
| **Resolved on Attempt 3** | 0 | 1 | +1 | Multi-attempt recovery |
| **Total Tokens** | 71,558 | 225,458 | +153,900 (3.15x) | Local Ollama token counter |
| **Prompt Tokens** | 66,826 | 211,821 | +144,995 (3.17x) | Detailed retry diagnostics |
| **Completion Tokens** | 4,732 | 13,637 | +8,905 (2.88x) | Candidate diffs and reasoning |
| **Total Duration (s)** | 482.99s (~8.0m) | 1,289.00s (~21.5m) | +806.01s (2.67x) | Wall-clock execution time |
| **Tokens / Successful Fix** | 8,944.8 | 17,342.9 | +8,398.1 (1.94x) | Tokens / resolved tasks |
| **Exact McNemar p-value** | — | — | **p = 0.0625** | Two-sided exact binomial (b=5, c=0) |
| **Financial Cost ($)** | **$0.00** | **$0.00** | $0.00 | 100% Local Ollama (`qwen2.5-coder:7b`) |
