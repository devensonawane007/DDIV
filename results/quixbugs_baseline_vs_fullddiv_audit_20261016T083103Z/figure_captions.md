# DDIV Phase 8.7: Publication Figure Captions and Interpretations

## Figure 1: QuixBugs 40-Task Benchmark: BASELINE vs FULL_DDIV Resolution
- **File:** `figures/figure_1_overall_resolution.png` (also `.svg`)
- **Caption:** Comparison of overall repair resolution rate across all 40 QuixBugs Python benchmark tasks between BASELINE (1 attempt, T=0.0, mechanisms disabled) and FULL_DDIV (up to 3 attempts, T=0.0 to 0.2, Supervisor guidance, FailureDetector, Episodic Memory, and Anti-Repetition Gate enabled). Evaluated using local Ollama (`qwen2.5-coder:7b`) with zero cloud invocations ($0.00 cost).
- **Interpretation:** FULL_DDIV achieves a resolution rate of 32.5% (13 / 40 tasks), representing an absolute improvement of +12.5 percentage points (+62.5% relative increase) over BASELINE (20.0%, 8 / 40 tasks). The exact two-sided McNemar test on discordant pairs yields p = 0.0625, reflecting a strong positive directional trend that approaches, but does not cross, the conventional alpha = 0.05 threshold due to bounded sample size (N=40).

---

## Figure 2: QuixBugs 40-Task Paired Outcomes Matrix
- **File:** `figures/figure_2_task_outcomes_matrix.png` (also `.svg`)
- **Caption:** Complete task-by-task paired resolution matrix across 40 canonical QuixBugs Python tasks. Green cells denote tasks passing 100% of specification tests; red cells denote unresolved defects. Red row labels indicate tasks where FULL_DDIV successfully recovered from an initial defect that BASELINE failed to resolve.
- **Interpretation:** The paired matrix illustrates complete non-inferiority: in no instance did BASELINE resolve a task that FULL_DDIV failed (c = 0). Eight tasks are one-shot solvable across both conditions (`bucketsort`, `find_first_in_sorted`, `flatten`, `is_valid_parenthesization`, `max_sublist_sum`, `pascal`, `rpn_eval`, `to_base`). Five tasks (`breadth_first_search`, `kth`, `levenshtein`, `quicksort`, `reverse_linked_list`) were uniquely recovered under FULL_DDIV via multi-attempt supervisory feedback.

---

## Figure 3: Paired Resolution Distribution and Contingency Analysis
- **File:** `figures/figure_3_paired_distribution.png` (also `.svg`)
- **Caption:** Distribution of paired binary outcomes across the 40 benchmark tasks into the four canonical contingency categories: Both Resolved (N = 8, 20.0%), FULL_DDIV Only (N = 5, 12.5%), BASELINE Only (N = 0, 0.0%), and Neither Resolved (N = 27, 67.5%).
- **Interpretation:** The contingency distribution confirms that discordant outcomes are strictly one-sided (b = 5, c = 0). The zero-regression result establishes that enabling DDIV mechanisms introduces no performance degradation on tasks solvable by the baseline model, while successfully rescuing 38.5% (5 of 13) of the total resolved task portfolio.

---

## Figure 4: Repair Attempts and Multi-Attempt Recovery Analysis
- **File:** `figures/figure_4_attempts_and_recovery.png` (also `.svg`)
- **Caption:** Left: Distribution of repair attempts executed per task under BASELINE (fixed at 1 attempt) versus FULL_DDIV (bounded at 3 attempts with early termination upon resolution). Right: Resolution stage breakdown for the 13 tasks resolved by FULL_DDIV.
- **Interpretation:** Under FULL_DDIV, 8 tasks terminated early on Attempt 1 (61.5% of resolved tasks), 4 tasks resolved on Attempt 2 (30.8%), and 1 task resolved on Attempt 3 (7.7%). Early stopping prevented unnecessary inference on 20.0% of all tasks, maintaining mean attempts per task at 2.40 rather than the theoretical maximum of 3.00.

---

## Figure 5: Resource and Token Consumption Trade-Offs
- **File:** `figures/figure_5_resource_efficiency.png` (also `.svg`)
- **Caption:** Resource and efficiency metrics comparing BASELINE and FULL_DDIV across four dimensions: aggregate token consumption, token cost per successful repair, total wall-clock duration, and mean latency per task. All inference ran locally via Ollama with zero financial API costs.
- **Interpretation:** FULL_DDIV consumed 225,458 total tokens compared to 71,558 tokens for BASELINE (a 3.15x increase), requiring 1,289.00s (~21.5 minutes) versus 482.99s (~8.0 minutes) total execution time. The token cost per successful repair rose from 8,945 tokens/fix in BASELINE to 17,343 tokens/fix in FULL_DDIV (a 1.94x increase), demonstrating the quantitative inference overhead required to achieve a +62.5% increase in repaired programs.

---

## Figure 6: Per-Attempt Patch Validity, Application, and Failure Breakdown
- **File:** `figures/figure_6_patch_evaluator_outcomes.png` (also `.svg`)
- **Caption:** Percentage breakdown of executed attempts across five evaluator stages: valid unified diff extracted, candidate patch applied cleanly against pristine git base revision, specification tests passed, evaluation timeout (15s ceiling), and syntax/indentation failure.
- **Interpretation:** BASELINE achieved a 92.5% patch extraction rate (37/40) and 82.5% patch application rate (33/40). FULL_DDIV achieved a 90.6% patch extraction rate (87/96) and 86.5% patch application rate (83/96). Timeouts occurred on 10.0% of BASELINE attempts and 11.5% of FULL_DDIV attempts (concentrated in non-terminating algorithmic loops: `bitcount`, `sqrt`, `topological_ordering`). Syntax errors occurred in 7.5% of BASELINE and 8.3% of FULL_DDIV attempts.

---

## Figure 7: FULL_DDIV Mechanism Invocations & Observational Recovery Associations
- **File:** `figures/figure_7_mechanism_evidence.png` (also `.svg`)
- **Caption:** Inventory of FULL_DDIV mechanisms showing invocation frequency (gray bars) alongside observational association with task recovery (green bars). Mechanisms include Supervisor Guidance, FailureDetector, Dynamic Temperature, Prior-Patch Diff Injection, Episodic Memory, Anti-Repetition Gate, and Trust Updates.
- **Interpretation:** Supervisor guidance, FailureDetector, and prompt negative anchors were active in all 56 multi-attempt retry runs, co-occurring with all 5 multi-attempt recoveries. The Anti-Repetition Gate triggered in 18 attempts and directly broke the greedy attractor in `quicksort`. Episodic memory logged 46 failure records to SQLite. Trust updates were not recorded in the standalone runner (0 events). These metrics demonstrate active mechanism engagement while emphasizing that individual mechanism causality cannot be decoupled without single-ablation runs.
