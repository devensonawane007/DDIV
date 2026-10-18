# DDIV Phase 8.7: Executive Summary — BASELINE vs FULL_DDIV Comparative Audit

## Scope and Core Question
This audit provides an exhaustive, strictly read-only comparative analysis of the completed Phase 8.6 QuixBugs automated program repair benchmark across all 40 canonical tasks, focusing strictly on **BASELINE** (1 attempt, mechanisms disabled, $T=0.0$) versus **FULL_DDIV** (up to 3 attempts, $T=0.0 	o 0.2$, Supervisor guidance, FailureDetector, Episodic Memory, and Anti-Repetition Gate enabled).

All 80 underlying condition runs utilized local Ollama (`qwen2.5-coder:7b`) with zero cloud invocations ($0.00 cost) and strict ground-truth isolation.

---

## Key Performance Findings

| Metric | BASELINE | FULL_DDIV | Absolute Delta | Relative Change | Statistical Significance |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Tasks Resolved** | 8 / 40 | 13 / 40 | **+5 tasks** | **+62.5%** | Exact McNemar $p = 0.0625$ |
| **Resolution Rate (%)** | **20.0%** | **32.5%** | **+12.5 pp** | **+62.5%** | Marginal trend ($p > 0.05$) |
| **Wilson 95% CI** | [10.5%, 34.8%] | [20.1%, 47.9%] | N/A | N/A | Partially overlapping CIs |
| **Both Resolved ($N_{\text{both}}$)** | 8 tasks (20.0%) | 8 tasks (20.0%) | — | — | Perfect baseline agreement |
| **FULL_DDIV Only ($N_{\text{FULL-only}}$)** | — | 5 tasks (12.5%) | +5 | — | Recovered on Attempts 2 & 3 |
| **BASELINE Only ($N_{\text{BASE-only}}$)** | 0 tasks (0.0%) | — | 0 | — | **Zero regressions ($c = 0$)** |
| **Neither Resolved ($N_{\text{neither}}$)** | 27 tasks (67.5%) | 27 tasks (67.5%) | — | — | Hard algorithmic defects |
| **Total Invocations** | 40 | 96 | +56 calls | +140.0% | $2.40$ attempts/task |
| **Total Tokens** | 71,558 | 225,458 | +153,900 | +215.1% | $5,636$ tokens/task |
| **Tokens per Fix** | 8,945 | 17,343 | +8,398 | +93.9% | Trade-off for +62.5% fixes |
| **Total Duration** | 482.99s (~8.0m) | 1,289.00s (~21.5m) | +806.01s | +166.9% | $32.23$s/task latency |
| **Cloud API Cost** | **$0.00** | **$0.00** | $0.00 | 0.0% | 100% Local Inference |

---

## 3 Core Takeaways for the Research Paper

1. **Defensible Improvement Claim:** FULL_DDIV achieves a +62.5% relative increase in resolved programs over BASELINE (+12.5 percentage points) with **zero regressions**. The 5 recovered tasks (`breadth_first_search`, `kth`, `levenshtein`, `quicksort`, `reverse_linked_list`) directly demonstrate multi-attempt supervisory recovery.
2. **Statistical Rigor & Claim Boundaries:** On 40 paired tasks, the exact McNemar test on discordant pairs ($b=5, c=0$) yields a two-sided p-value of **0.0625**. Because $p > 0.05$, the paper must describe the result as a strong positive directional trend rather than a formally statistically significant difference.
3. **Resource Trade-Off:** Achieving this repair expansion requires a 3.15x increase in tokens and a 2.67x increase in runtime, with tokens per successful repair rising from 8,945 to 17,343.
