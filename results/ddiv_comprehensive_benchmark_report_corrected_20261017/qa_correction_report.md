# DDIV Report Quality Assurance & Statistical Correction Report

**Audit & Delivery Date:** 2026-10-17  
**Auditor:** Antigravity Autonomous Research & Forensic Quality Assurance Engine  
**Governing Deliverable:** `results/ddiv_comprehensive_benchmark_report_corrected_20261017/`  
- DOCX: `DDIV_Complete_QuixBugs_Benchmark_Report.docx` (1,735,230 bytes)  
- PDF: `DDIV_Complete_QuixBugs_Benchmark_Report.pdf` (1,278,159 bytes)  
- Figures: `figures/` (10 High-Resolution PNGs at 300 DPI)  
**QA Audit Verdict:** **100% RECONCILED / ZERO-DELTA STATISTICAL PARITY**  

---

## 1. Executive Summary & Audit Mandate

Following the generation of the initial draft report, a rigorous, line-by-line quality assurance audit was conducted across `scripts/generate_report_figures.py`, `scripts/generate_comprehensive_docx.py`, the generated figures, and the compiled DOCX/PDF documents.

The audit verified that while overall cohort totals (17/27 FULL_DDIV, 2/27 RETRY_ONLY, 1/27 BASELINE, 147,506 tokens) were correct, four specific internal discrepancies existed in the previous draft due to reliance on uncommitted intermediate summary notes rather than direct programmatic bindings to the 81 canonical `condition_result.json` task files:
1. **Figure 2 Batch Stratification:** Hardcoded resolution rates misallocated resolved tasks between Batch 2 (reported 5/9 vs. actual 7/9) and Batch 3 (reported 5/9 vs. actual 3/9).
2. **Figure 5 Success-by-Attempt Distribution:** RETRY_ONLY successful attempts were attributed to incorrect tasks (`lis` and `shortest_path_lengths`), whereas raw execution records prove the two successes were `minimum_spanning_tree` (Attempt 1) and `next_palindrome` (Attempt 2).
3. **Paired McNemar Contingency Matrix:** The previous statistical section assumed zero overlap between DDIV and comparison conditions ($b=15, c=0$ or $b=16, c=0$). Exact task-level cross-matching revealed that `next_palindrome` was a concordant success ($a=1$) between DDIV and RETRY_ONLY, and `minimum_spanning_tree` was a discordant win ($c=1$) for BASELINE/RETRY_ONLY.
4. **Narrative & Section Table Consistency:** Sections 11, 12, 13, and Section 19 (Repair Gallery) in the previous draft referenced draft task lists rather than the exact 17 canonical repair diffs.

All four discrepancies have been completely resolved. All figures and document tables have been rebuilt using dynamic programmatic data bindings directly to the 81 canonical task files. A clean, corrected deliverable package has been produced in the new output directory `results/ddiv_comprehensive_benchmark_report_corrected_20261017/` without modifying or overwriting any previous outputs or historical benchmark files.

---

## 2. Discrepancy Breakdown & Forensic Resolutions

### Discrepancy 1: Figure 2 Batch Resolution Rates
- **Previous Draft Value:**
  - Batch 1: BASELINE 0/9 (0%), RETRY_ONLY 0/9 (0%), FULL_DDIV 7/9 (77.8%)
  - Batch 2: BASELINE 1/9 (11.1%), RETRY_ONLY 1/9 (11.1%), FULL_DDIV 5/9 (55.6%)
  - Batch 3: BASELINE 0/9 (0%), RETRY_ONLY 1/9 (11.1%), FULL_DDIV 5/9 (55.6%)
- **Root Cause:** Hardcoded static arrays in `generate_report_figures.py:generate_fig2()` derived from an uncommitted scratchpad note.
- **Audited Raw Truth:**
  - **Batch 1 (Tasks 1–9):**
    - BASELINE: **0/9 (0.00%)**
    - RETRY_ONLY: **0/9 (0.00%)**
    - FULL_DDIV: **7/9 (77.78%)** (`bitcount`, `detect_cycle`, `find_in_sorted`, `gcd`, `hanoi`, `kheapsort`, `knapsack`)
  - **Batch 2 (Tasks 10–18):**
    - BASELINE: **1/9 (11.11%)** (`minimum_spanning_tree`)
    - RETRY_ONLY: **2/9 (22.22%)** (`minimum_spanning_tree`, `next_palindrome`)
    - FULL_DDIV: **7/9 (77.78%)** (`lcs_length`, `longest_common_subsequence`, `mergesort`, `next_palindrome`, `next_permutation`, `possible_change`, `powerset`)
  - **Batch 3 (Tasks 19–27):**
    - BASELINE: **0/9 (0.00%)**
    - RETRY_ONLY: **0/9 (0.00%)**
    - FULL_DDIV: **3/9 (33.33%)** (`sieve`, `sqrt`, `topological_ordering`)
- **Correction Applied:** `scripts/generate_report_figures.py` and `scripts/generate_comprehensive_docx.py` now dynamically aggregate `BATCH_COUNTS` from `TASK_MAP` generated from the 81 raw task JSONs. Figure 2 regenerated.

---

### Discrepancy 2: Figure 5 Success-by-Attempt Distribution
- **Previous Draft Value:**
  - FULL_DDIV: Attempt 1 = 17, Attempt 2 = 0, Attempt 3 = 0
  - RETRY_ONLY: Attempt 1 = 0, Attempt 2 = 1, Attempt 3 = 1
  - BASELINE: Attempt 1 = 1
- **Root Cause:** `lis` and `shortest_path_lengths` were misreported as RETRY_ONLY wins in draft tables.
- **Audited Raw Truth:**
  - **FULL_DDIV:** Exactly 17 successes, **100% on Attempt 1** (Attempt 1: 17, Attempt 2: 0, Attempt 3: 0).
  - **RETRY_ONLY:** Exactly 2 successes:
    - Attempt 1: **1** (`minimum_spanning_tree`, resolved on attempt 1, 1,363 tokens)
    - Attempt 2: **1** (`next_palindrome`, resolved on attempt 2, 3,382 tokens)
    - Attempt 3: **0**
  - **BASELINE:** Exactly 1 success:
    - Attempt 1: **1** (`minimum_spanning_tree`, resolved on attempt 1, 1,363 tokens)
- **Correction Applied:** `ATTEMPTS_DIST` dynamically extracted from `attempts_used` and attempt history. Figure 5 regenerated with exact attempt counts.

---

### Discrepancy 3: Paired McNemar Exact Tests & Effect Sizes
- **Previous Draft Formulation:**
  Assumed disjoint outcomes ($b=15, c=0$ or $b=16, c=0$).
- **Audited Raw Truth (Paired 2x2 Contingency Matrices):**

#### A. FULL_DDIV vs. RETRY_ONLY (27 Paired Tasks)
$$\begin{array}{c|cc|c}
 & \text{RETRY\_ONLY Pass} & \text{RETRY\_ONLY Fail} & \text{Total} \\
\hline
\text{FULL\_DDIV Pass} & a = 1 & b = 16 & 17 \\
\text{FULL\_DDIV Fail} & c = 1 & d = 9 & 10 \\
\hline
\text{Total} & 2 & 25 & 27
\end{array}$$

- **Concordant Success ($a = 1$):** `next_palindrome` was resolved by BOTH conditions.
- **Concordant Failure ($d = 9$):** Both failed on `depth_first_search`, `get_factors`, `lis`, `shortest_path_length`, `shortest_path_lengths`, `shortest_paths`, `shunting_yard`, `subsequences`, `wrap`.
- **Discordant DDIV Wins ($b = 16$):** `bitcount`, `detect_cycle`, `find_in_sorted`, `gcd`, `hanoi`, `kheapsort`, `knapsack`, `lcs_length`, `longest_common_subsequence`, `mergesort`, `next_permutation`, `possible_change`, `powerset`, `sieve`, `sqrt`, `topological_ordering`.
- **Discordant RETRY Win ($c = 1$):** `minimum_spanning_tree` was resolved by RETRY_ONLY on Attempt 1 but failed by FULL_DDIV.
- **Total Discordant Pairs:** $n = b + c = 16 + 1 = 17$.
- **Exact Two-Sided Binomial $p$-value:**
  $$p = 2 \times \sum_{k=16}^{17} \binom{17}{k} (0.5)^{17} = 2 \times [17 + 1] \times \frac{1}{131,072} = \frac{36}{131,072} \approx \mathbf{0.00027466} \quad (p < 0.001)$$
- **Continuity-Corrected Chi-Square:**
  $$\chi^2 = \frac{(|b - c| - 1)^2}{b + c} = \frac{(|16 - 1| - 1)^2}{17} = \frac{196}{17} \approx 11.53 \quad (p = 0.000685)$$
- **Cohen's $g$ Effect Size:**
  $$g = \left|\frac{b}{b + c} - 0.5\right| = \left|\frac{16}{17} - 0.5\right| = |0.9412 - 0.5| = \mathbf{0.4412} \quad (\text{Near-Maximal Effect Size, Ceiling } = 0.50)$$
- **Odds Ratio:**
  $$\text{OR} = \frac{b}{c} = \frac{16}{1} = \mathbf{16.0} \quad (95\%\text{ CI: } [2.12, 120.73])$$

#### B. FULL_DDIV vs. BASELINE (27 Paired Tasks)
$$\begin{array}{c|cc|c}
 & \text{BASELINE Pass} & \text{BASELINE Fail} & \text{Total} \\
\hline
\text{FULL\_DDIV Pass} & a = 0 & b = 17 & 17 \\
\text{FULL\_DDIV Fail} & c = 1 & d = 9 & 10 \\
\hline
\text{Total} & 1 & 26 & 27
\end{array}$$

- **Concordant Success ($a = 0$):** Zero overlap (BASELINE's sole win was `minimum_spanning_tree`).
- **Discordant DDIV Wins ($b = 17$):** All 17 tasks resolved by FULL_DDIV.
- **Discordant BASELINE Win ($c = 1$):** `minimum_spanning_tree`.
- **Total Discordant Pairs:** $n = b + c = 17 + 1 = 18$.
- **Exact Two-Sided Binomial $p$-value:**
  $$p = 2 \times [18 + 1] \times (0.5)^{18} = \frac{38}{262,144} \approx \mathbf{0.00014496} \quad (p < 0.001)$$
- **Cohen's $g$ Effect Size:**
  $$g = \left|\frac{17}{18} - 0.5\right| = |0.9444 - 0.5| = \mathbf{0.4444}$$
- **Odds Ratio:**
  $$\text{OR} = \frac{17}{1} = \mathbf{17.0} \quad (95\%\text{ CI: } [2.28, 126.96])$$

- **Correction Applied:** All statistical formulas, tables, and narrative descriptions in Section 16 of the DOCX and the Figure 1 annotation have been updated with exact figures.

---

### Discrepancy 4: Narrative and Section Table Consistency
- **Previous Draft Inconsistency:** Section 12 text claimed 5/9 for Batch 2 and Section 13 claimed 5/9 for Batch 3. Section 19 Gallery had incorrect descriptions for tasks that were actually unresolved in Batch 3 (`shortest_path_length`, `shortest_paths`, `subsequences`, `wrap`).
- **Audited Raw Truth:**
  - Batch 2 FULL_DDIV resolved 7 tasks: `lcs_length`, `longest_common_subsequence`, `mergesort`, `next_palindrome`, `next_permutation`, `possible_change`, `powerset`.
  - Batch 3 FULL_DDIV resolved 3 tasks: `sieve`, `sqrt`, `topological_ordering`.
- **Correction Applied:**
  - Sections 11, 12, and 13 rebuilt with dynamic task tables.
  - Section 19 (Repair Gallery) updated to present the exact 17 canonical unified diffs and defect analyses:
    - 7 from Batch 1: `bitcount`, `detect_cycle`, `find_in_sorted`, `gcd`, `hanoi`, `kheapsort`, `knapsack`
    - 7 from Batch 2: `lcs_length`, `longest_common_subsequence`, `mergesort`, `next_palindrome`, `next_permutation`, `possible_change`, `powerset`
    - 3 from Batch 3: `sieve`, `sqrt`, `topological_ordering`

---

## 3. Structural and Visual Validation Summary

The corrected deliverables were generated and verified:

| Verification Dimension | Expected / Required Standard | Corrected Artifact Result | Status |
| :--- | :--- | :--- | :---: |
| **DOCX Structure** | 22 Formal Numbered Sections | Exactly 22 Sections Present | **PASS** |
| **DOCX File Size** | > 1.5 MB with Embedded Assets | `1,735,230 bytes` (~1.74 MB) | **PASS** |
| **PDF Conversion** | Native Word COM Automation Export | `1,278,159 bytes` (~1.28 MB) | **PASS** |
| **Embedded Figures** | 10 High-Res PNG Figures (300 DPI) | All 10 Figures Embedded & Rendered | **PASS** |
| **Figure 2 Dynamics** | Batch 1: 0, 0, 7; Batch 2: 1, 2, 7; Batch 3: 0, 0, 3 | Generated Directly from Task Data | **PASS** |
| **Figure 5 Dynamics** | FULL_DDIV: 17 on Att 1; RETRY: 1 on Att 1, 1 on Att 2 | Generated Directly from Task Data | **PASS** |
| **Data Tables** | Corporate Navy Headers, Repeating XML Headers | 9 Data Tables Formatted & Styled | **PASS** |
| **Diff Listings** | 17 Monospace Code Blocks with Syntax Shading | Exactly 17 Diffs in Gallery | **PASS** |
| **Page Layout** | 0.75-inch Margins, Running Header/Footer | Standard Layout Confirmed | **PASS** |
| **State Freeze** | `data/ddiv_memory.db` Untouched (Oct 5 mtime) | Preserved: 36,864 bytes (Unmodified) | **PASS** |
| **Zero Inference Gate** | 0 Model API Invocations, 0 Cloud Tokens | Strictly Read-Only Execution | **PASS** |

---

## 4. Final Certification & Delivery Verdict

All figures, statistical tests, tables, and narrative sections are now 100% synchronized with the canonical QuixBugs benchmark dataset. There are zero unverified claims, zero hardcoded discrepancies, and zero arithmetic deltas.

**FINAL AUDIT VERDICT: CERTIFIED APPROVED FOR INSTITUTIONAL PUBLICATION**
