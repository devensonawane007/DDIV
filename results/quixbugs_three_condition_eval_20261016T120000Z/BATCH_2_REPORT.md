# DDIV Phase 8.9.5: Batch 2 Comprehensive Comparative Benchmark Report

**Batch:** 2 of 3 (Tasks 10–18 of 27)  
**Evaluation Mode:** `ALL` Conditions (`BASELINE`, `RETRY_ONLY`, `FULL_DDIV`)  
**Evaluation Date:** 2026-10-17  
**Artifact Version:** 1.0 (Modular for Multi-Batch Synthesis)  
**Primary Dataset:** QuixBugs Python Benchmark  
**Evaluation Output Directory:** [`results/quixbugs_three_condition_eval_20261016T120000Z/`](file:///d:/PROJECTS/DDIV/results/quixbugs_three_condition_eval_20261016T120000Z/)  

---

## 1. Executive Summary & Core Research Findings

In Batch 2 of the DDIV comparative evaluation, 9 challenging QuixBugs programs were evaluated under all three experimental conditions:

1. **`BASELINE` (No Feedback):** Single attempt using local Ollama `qwen2.5-coder:7b`. No supervisor, tester, memory, or iterative feedback.
2. **`RETRY_ONLY` (Test Diagnostics Only):** Up to 3 attempts using local Ollama `qwen2.5-coder:7b` receiving raw sanitized pytest failure tracebacks upon test failure.
3. **`FULL_DDIV` (Hybrid Multi-Agent Dynamic Dual-Intervention Verification):** Option A Hybrid configuration combining Gemini `gemini-3.1-flash-lite` (Fault Localization), Groq `qwen/qwen3.8-27b` (Supervisor & Adversarial Tester), local Ollama `qwen2.5-coder:7b` (Coder), plus cross-attempt Trust calibration and Episodic Memory.

### Key Empirical Findings

```mermaid
%%{init: {'theme': 'neutral'}}%%
graph LR
    subgraph Batch 2 Performance (Tasks 10 to 18)
        B["BASELINE (Local 7B)<br/>1 / 9 (11.1%)<br/>15,529 Tokens"]
        R["RETRY_ONLY (Local 7B + Pytest)<br/>2 / 9 (22.2%)<br/>50,972 Tokens"]
        F["FULL_DDIV (Option A Hybrid)<br/>7 / 9 (77.8%)<br/>44,780 Tokens"]
    end
    
    style B fill:#fee,stroke:#e66,stroke-width:2px
    style R fill:#fdd,stroke:#c33,stroke-width:2px
    style F fill:#efe,stroke:#2a2,stroke-width:3px
```

- **Replicated 77.8% Resolution in `FULL_DDIV`:** For the second consecutive batch, `FULL_DDIV` achieved exactly **7 / 9 (77.8%) resolution**, demonstrating stable, robust multi-agent repair dynamics across completely distinct algorithmic problem classes.
- **Persistent Token Inefficiency in Unsupervised Retries:** `RETRY_ONLY` burned **50,972 tokens across 24 attempts** to resolve only 2 tasks (22.2%), whereas `FULL_DDIV` resolved **7 tasks in 13 attempts using 44,780 tokens** (12.1% fewer tokens, 3.5x higher resolution).
- **One-Shot Convergence Preserved:** All 7 tasks resolved by `FULL_DDIV` were solved on **Attempt 1** (1.0 attempts to resolution), demonstrating that supervisory architectural context prevents trial-and-error thrashing.

---

## 2. High-Level Performance Comparison Table (Batch 2)

| Metric | `BASELINE` | `RETRY_ONLY` | `FULL_DDIV` | Advantage / Impact |
| :--- | :---: | :---: | :---: | :--- |
| **Tasks Evaluated** | 9 | 9 | 9 | Tasks 10–18 from canonical manifest |
| **Resolved Tasks** | **1** | **2** | **7** | **+55.6 percentage points** over Retry-Only |
| **Resolution Rate (%)** | **11.1%** | **22.2%** | **77.8%** | Decisive multi-agent advantage |
| **Total Attempts Used** | 9 | 24 | 13 | DDIV terminated early on 7 tasks (1.4 att/task) |
| **Mean Attempts / Task** | 1.0 | 2.7 | 1.4 | Retry-Only failed to converge on 7/9 tasks |
| **Attempts to Resolution** | 1.0 | 1.5 | **1.0** | All 7 DDIV repairs succeeded on Attempt 1 |
| **Total Tokens Consumed** | 15,529 | 50,972 | 44,780 | DDIV used 6,192 fewer tokens than Retry-Only |
| **Mean Tokens / Task** | 1,725 | 5,664 | 4,976 | Guided convergence saves inference budget |
| **Total Wall-Clock Time** | 126.2s | 383.2s | 576.7s | Pacing delay & dual-oracle verification |
| **Mean Latency / Task** | 14.0s | 42.6s | 64.1s | Comprehensive verification tradeoff |
| **Cloud Token Cost ($)** | $0.00 | $0.00 | $0.00 | Free tiers utilized (0 paid calls) |

---

## 3. Per-Task 3-Way Comparative Matrix (Batch 2)

| Program Name | `BASELINE` (Local) | `RETRY_ONLY` (Local) | `FULL_DDIV` (Option A) | Dominant Outcome |
| :--- | :--- | :--- | :--- | :---: |
| [`lcs_length`](file:///d:/PROJECTS/DDIV/python_programs/lcs_length.py) | **FAIL** (att=1, 1,650t, 23.7s)<br/>*Assertion failure* | **FAIL** (att=3, 9,109t, 49.0s)<br/>*Assertion failure across atts* | **PASS** (att=1, 3,285t, 76.6s)<br/>*DP diagonal index: `dp[i-1, j-1] + 1`* | **FULL_DDIV Only** |
| [`lis`](file:///d:/PROJECTS/DDIV/python_programs/lis.py) | **FAIL** (att=1, 2,014t, 26.8s)<br/>*Assertion failure* | **FAIL** (att=3, 8,536t, 68.0s)<br/>*Assertion failure across atts* | **FAIL** (att=3, 13,494t, 141.5s)<br/>*Endpoint dictionary key bound error* | **Unresolved Cohort** |
| [`longest_common_subsequence`](file:///d:/PROJECTS/DDIV/python_programs/longest_common_subsequence.py) | **FAIL** (att=1, 1,693t, 10.0s)<br/>*Assertion failure* | **FAIL** (att=3, 5,224t, 30.9s)<br/>*Assertion failure across atts* | **PASS** (att=1, 3,157t, 48.6s)<br/>*Slicing recursion: `b[1:]` advance* | **FULL_DDIV Only** |
| [`mergesort`](file:///d:/PROJECTS/DDIV/python_programs/mergesort.py) | **FAIL** (att=1, 1,555t, 5.9s)<br/>*Empty patch / no mod* | **FAIL** (att=3, 4,710t, 15.9s)<br/>*Empty patch across all 3 atts* | **PASS** (att=1, 3,158t, 45.4s)<br/>*Base case condition: `len(arr) <= 1`* | **FULL_DDIV Only** |
| [`minimum_spanning_tree`](file:///d:/PROJECTS/DDIV/python_programs/minimum_spanning_tree.py) | **PASS** (att=1, 1,801t, 14.9s)<br/>*Union-find group update loop* | **PASS** (att=1, 1,801t, 12.9s)<br/>*Union-find group update loop* | **FAIL** (att=3, 8,259t, 50.0s)<br/>*Undefined variable `set_v` static check* | **BASELINE & RETRY** |
| [`next_palindrome`](file:///d:/PROJECTS/DDIV/python_programs/next_palindrome.py) | **FAIL** (att=1, 1,832t, 15.4s)<br/>*Assertion failure* | **PASS** (att=2, 3,620t, 45.5s)<br/>*Zero multiplier: `len - 1`* | **PASS** (att=1, 3,870t, 52.1s)<br/>*Zero multiplier: `len - 1`* | **RETRY & DDIV** |
| [`next_permutation`](file:///d:/PROJECTS/DDIV/python_programs/next_permutation.py) | **FAIL** (att=1, 1,644t, 12.4s)<br/>*Assertion failure* | **FAIL** (att=3, 7,135t, 52.7s)<br/>*Assertion failure across atts* | **PASS** (att=1, 3,156t, 57.7s)<br/>*Inversion check: `perm[j] > perm[i]`* | **FULL_DDIV Only** |
| [`possible_change`](file:///d:/PROJECTS/DDIV/python_programs/possible_change.py) | **FAIL** (att=1, 1,785t, 10.9s)<br/>*AST indentation error* | **FAIL** (att=3, 6,108t, 89.7s)<br/>*Empty patch on att 3* | **PASS** (att=1, 3,448t, 60.0s)<br/>*Base case: `total < 0 or not coins`* | **FULL_DDIV Only** |
| [`powerset`](file:///d:/PROJECTS/DDIV/python_programs/powerset.py) | **FAIL** (att=1, 1,555t, 6.3s)<br/>*Empty patch / no mod* | **FAIL** (att=3, 4,729t, 18.7s)<br/>*Empty patch across all 3 atts* | **PASS** (att=1, 2,953t, 44.9s)<br/>*Recursive subset union concatenation* | **FULL_DDIV Only** |

---

## 4. Cumulative Multi-Batch Progression (18 of 27 Tasks)

```mermaid
%%{init: {'theme': 'neutral'}}%%
graph TD
    subgraph Cumulative Progress (Tasks 1 to 18)
        CB["BASELINE Cumulative<br/>1 / 18 (5.6%)<br/>30,191 Tokens"]
        CR["RETRY_ONLY Cumulative<br/>2 / 18 (11.1%)<br/>109,475 Tokens"]
        CF["FULL_DDIV Cumulative<br/>14 / 18 (77.8%)<br/>89,519 Tokens"]
    end

    style CB fill:#fee,stroke:#e66,stroke-width:2px
    style CR fill:#fdd,stroke:#c33,stroke-width:2px
    style CF fill:#efe,stroke:#2a2,stroke-width:3px
```

### Cumulative Cross-Batch Summary (Batches 1 & 2 Combined)

| Metric | `BASELINE` | `RETRY_ONLY` | `FULL_DDIV` | Advantage of `FULL_DDIV` |
| :--- | :---: | :---: | :---: | :--- |
| **Batch 1 Resolved (Tasks 1–9)** | 0 / 9 (0.0%) | 0 / 9 (0.0%) | 7 / 9 (77.8%) | +77.8 pp |
| **Batch 2 Resolved (Tasks 10–18)**| 1 / 9 (11.1%) | 2 / 9 (22.2%) | 7 / 9 (77.8%) | +55.6 pp |
| **Total Resolved (18 Tasks)** | **1 / 18** | **2 / 18** | **14 / 18** | **+66.7 pp over RETRY_ONLY** |
| **Cumulative Resolution Rate** | **5.6%** | **11.1%** | **77.8%** | **7.0x Higher Resolution** |
| **Total Attempts (18 Tasks)** | 18 | 51 | 26 | 49.0% fewer attempts |
| **Total Tokens Consumed** | 30,191 | 109,475 | 89,519 | **19,956 fewer tokens than RETRY_ONLY** |
| **Mean Tokens / Resolved Task** | 30,191 | 54,738 | **6,394** | **8.6x More Token-Efficient** |

> [!IMPORTANT]
> **Macro-Level Finding:**  
> Across 18 tasks, giving local `qwen2.5-coder:7b` unsupervised iterative retries (`RETRY_ONLY`) burned **109,475 tokens to resolve only 2 bugs** (54,738 tokens per resolved bug). In contrast, the multi-agent `FULL_DDIV` framework resolved **14 bugs using 89,519 tokens** (6,394 tokens per resolved bug), achieving **8.6x greater token efficiency per successful repair**.

---

## 5. Token & Daily Budget Ledger

```json
{
  "last_updated": "2026-10-17T07:17:16Z",
  "today_date_utc": "2026-10-17",
  "today_usage": {
    "gemini": { "prompt": 2739, "completion": 5224, "total": 7963 },
    "groq":   { "prompt": 3825, "completion": 1672, "total": 5497 },
    "ollama": { "prompt": 91000, "completion": 6821, "total": 97821 }
  },
  "today_ceilings": {
    "groq_ceiling": 100000,
    "gemini_ceiling": 30000,
    "groq_remaining": 94503,
    "gemini_remaining": 22037
  }
}
```

- **Groq Token Usage Today:** 5,497 / 100,000 (**94,503 tokens remaining**, 94.5% available).
- **Gemini Token Usage Today:** 7,963 / 30,000 (**22,037 tokens remaining**, 73.5% available).
- **Production State:** Pristine (`data/ddiv_memory.db` has 0 QuixBugs records; Mon Oct 5 mtime preserved).

---

## 6. Patch Gallery: The 7 Canonical FULL_DDIV Repairs (Batch 2)

### 1. `lcs_length` (Dynamic Programming Diagonal Transition)
```diff
--- a/python_programs/lcs_length.py
+++ b/python_programs/lcs_length.py
@@ -6,7 +6,7 @@
     for i in range(len(s)):
         for j in range(len(t)):
             if s[i] == t[j]:
-                dp[i, j] = dp[i - 1, j] + 1
+                dp[i, j] = dp[i - 1, j - 1] + 1
 
     return max(dp.values()) if dp else 0
```

### 2. `longest_common_subsequence` (Recursive Slicing Advance)
```diff
--- a/python_programs/longest_common_subsequence.py
+++ b/python_programs/longest_common_subsequence.py
@@ -3,7 +3,7 @@
         return ''
 
     elif a[0] == b[0]:
-        return a[0] + longest_common_subsequence(a[1:], b)
+        return a[0] + longest_common_subsequence(a[1:], b[1:])
 
     else:
         return max(
```

### 3. `mergesort` (Divide & Conquer Base Case)
```diff
--- a/python_programs/mergesort.py
+++ b/python_programs/mergesort.py
@@ -14,7 +14,7 @@
         result.extend(left[i:] or right[j:])
         return result
 
-    if len(arr) == 0:
+    if len(arr) <= 1:
         return arr
     else:
         middle = len(arr) // 2
```

### 4. `next_palindrome` (Zero Padding Multiplier Calculation)
```diff
--- a/python_programs/next_palindrome.py
+++ b/python_programs/next_palindrome.py
@@ -12,7 +12,7 @@
             if low_mid != high_mid:
                 digit_list[low_mid] += 1
             return digit_list
-    return [1] + (len(digit_list)) * [0] + [1]
+    return [1] + (len(digit_list) - 1) * [0] + [1]
```

### 5. `next_permutation` (Inversion Comparison Predicate)
```diff
--- a/python_programs/next_permutation.py
+++ b/python_programs/next_permutation.py
@@ -3,7 +3,7 @@
     for i in range(len(perm) - 2, -1, -1):
         if perm[i] < perm[i + 1]:
             for j in range(len(perm) - 1, i, -1):
-                if perm[j] < perm[i]:
+                if perm[j] > perm[i]:
                     next_perm = list(perm)
                     next_perm[i], next_perm[j] = perm[j], perm[i]
                     next_perm[i + 1:] = reversed(next_perm[i + 1:])
```

### 6. `possible_change` (Coin Change Non-Negative Base Case)
```diff
--- a/python_programs/possible_change.py
+++ b/python_programs/possible_change.py
@@ -2,7 +2,7 @@
 def possible_change(coins, total):
     if total == 0:
         return 1
-    if total < 0:
+    if total < 0 or not coins:
         return 0
 
     first, *rest = coins
```

### 7. `powerset` (Recursive Subsets Concatenation)
```diff
--- a/python_programs/powerset.py
+++ b/python_programs/powerset.py
@@ -3,7 +3,7 @@
     if arr:
         first, *rest = arr #python3 just like car and cdr (in this case anyway..)
         rest_subsets = powerset(rest)
-        return [[first] + subset for subset in rest_subsets]
+        return rest_subsets + [[first] + subset for subset in rest_subsets]
     else:
         return [[]]
```

---

## 7. Readiness for Final Batch 3 (Tasks 19–27)

With **Batch 2 complete**, 18 of 27 tasks are now evaluated. With **94.5% of Groq quota** and **73.5% of Gemini quota** remaining today:
- **Batch 3 Tasks (9 tasks):** `quickselect`, `quicksort`, `rpn_eval`, `shunting_yard`, `sieve`, `sqrt`, `subsequences`, `to_base`, `wrap`.
- **Observations:** 27 observations (9 `BASELINE`, 9 `RETRY_ONLY`, 9 `FULL_DDIV`).
- Upon completion of Batch 3, all 81 comparative observations will be finished, allowing generation of the final 27-task omnibus comparative benchmark report.
