# DDIV Phase 8.9.5: Batch 1 Comprehensive Comparative Benchmark Report

**Batch:** 1 of 3 (Tasks 1–9 of 27)  
**Evaluation Mode:** `ALL` Conditions (`BASELINE`, `RETRY_ONLY`, `FULL_DDIV`)  
**Evaluation Date:** 2026-10-16  
**Artifact Version:** 1.0 (Modular for Multi-Batch Synthesis)  
**Primary Dataset:** QuixBugs Python Benchmark  
**Evaluation Output Directory:** [`results/quixbugs_three_condition_eval_20261016T120000Z/`](file:///d:/PROJECTS/DDIV/results/quixbugs_three_condition_eval_20261016T120000Z/)  

---

## 1. Executive Summary & Core Research Findings

In Batch 1 of the DDIV comparative evaluation, 9 screened, previously unresolved QuixBugs programs were evaluated under three strictly controlled experimental conditions on the exact same task instances:

1. **`BASELINE` (No Feedback):** Single attempt using local Ollama `qwen2.5-coder:7b`. No supervisor, tester, memory, or iterative feedback.
2. **`RETRY_ONLY` (Test Diagnostics Only):** Up to 3 attempts using local Ollama `qwen2.5-coder:7b` receiving raw sanitized pytest failure tracebacks upon test failure. No supervisor, tester, episodic memory, or trust dynamics.
3. **`FULL_DDIV` (Hybrid Multi-Agent Dynamic Dual-Intervention Verification):** Option A Hybrid configuration combining Gemini `gemini-3.1-flash-lite` (Fault Localization), Groq `qwen/qwen3.8-27b` (Supervisor & Adversarial Tester), local Ollama `qwen2.5-coder:7b` (Coder), plus cross-attempt Trust calibration and Episodic Memory.

### Key Empirical Findings

```mermaid
%%{init: {'theme': 'neutral'}}%%
graph LR
    subgraph Comparative Performance on Identical 9 Tasks
        B["BASELINE (Local 7B)<br/>0 / 9 (0.0%)<br/>14,662 Tokens"]
        R["RETRY_ONLY (Local 7B + Pytest)<br/>0 / 9 (0.0%)<br/>58,503 Tokens"]
        F["FULL_DDIV (Hybrid Multi-Agent)<br/>7 / 9 (77.8%)<br/>44,739 Tokens"]
    end
    
    style B fill:#fee,stroke:#e66,stroke-width:2px
    style R fill:#fdd,stroke:#c33,stroke-width:2px
    style F fill:#efe,stroke:#2a2,stroke-width:3px
```

- **Supervision is Decisive:** On this difficult task cohort, local LLM retries alone with standard test diagnostics achieved **0.0% resolution (0/9)** despite consuming 27 attempts and 58,503 tokens. Conversely, `FULL_DDIV` achieved **77.8% resolution (7/9)** on the exact same programs.
- **The "Retry Trap" Phenomenon:** Unsupervised test-feedback loops (`RETRY_ONLY`) burned **30.8% more tokens** than `FULL_DDIV` (58,503 vs 44,739 tokens) because the model repeatedly hallucinated invalid diff anchors or oscillated between invalid syntax hypotheses across 3 failed attempts per task.
- **Single-Attempt Resolution Efficiency:** In `FULL_DDIV`, **all 7 resolved tasks were solved on Attempt 1** (100% of repairs were one-shot when guided by Fault Localization and Supervisory Guidance), needing only 1.4 attempts on average across all 9 tasks.

---

## 2. Experimental Setup & Architectural Contrast

```mermaid
flowchart TD
    subgraph Condition 1: BASELINE
        P1[Buggy Code & Task Description] --> C1[Local Coder: qwen2.5-coder:7b]
        C1 --> O1[Single Attempt Patch]
        O1 --> V1{Pytest Oracle}
    end

    subgraph Condition 2: RETRY_ONLY
        P2[Buggy Code & Task Description] --> C2[Local Coder: qwen2.5-coder:7b]
        C2 --> O2[Attempt Patch]
        O2 --> V2{Pytest Oracle}
        V2 -- "Fail (<=3 attempts)" --> FB[Raw Sanitized Pytest Output]
        FB --> C2
    end

    subgraph Condition 3: FULL_DDIV
        P3[Buggy Code] --> LOC[Gemini Flash-Lite: Fault Localization]
        LOC --> SUP[Groq Qwen-27B: Supervisory Plan]
        EM[(Episodic Memory)] <--> SUP
        SUP --> C3[Local Coder: qwen2.5-coder:7b]
        C3 --> O3[Candidate Patch]
        O3 --> TST[Groq Qwen-27B: Adversarial Unit Tests]
        TST --> V3{Dual Oracle: Pytest + TST}
        V3 -- "Evaluate" --> TRU[Trust Calibration & Memory Store]
        TRU -. "Update" .-> SUP
    end

    style Condition 1: BASELINE fill:#f9f9f9,stroke:#999
    style Condition 2: RETRY_ONLY fill:#fff2f2,stroke:#d9534f
    style Condition 3: FULL_DDIV fill:#f0fff0,stroke:#5cb85c
```

---

## 3. High-Level Performance Comparison Table

| Metric | `BASELINE` | `RETRY_ONLY` | `FULL_DDIV` | Advantage / Impact |
| :--- | :---: | :---: | :---: | :--- |
| **Tasks Evaluated** | 9 | 9 | 9 | Fixed cohort from Phase 8.8 unresolved set |
| **Resolved Tasks** | **0** | **0** | **7** | **+77.8 percentage points** |
| **Resolution Rate (%)** | **0.0%** | **0.0%** | **77.8%** | Statistically decisive superiority |
| **Total Attempts Used** | 9 | 27 | 13 | DDIV stopped early on success (1.4 att/task) |
| **Mean Attempts / Task** | 1.0 | 3.0 | 1.4 | RETRY_ONLY exhausted max attempts every time |
| **Attempts to Resolution** | N/A | N/A | **1.0** | 100% of solved tasks resolved on Attempt 1 |
| **Total Tokens Consumed** | 14,662 | 58,503 | 44,739 | DDIV used **13,764 fewer tokens** than RETRY_ONLY |
| **Mean Tokens / Task** | 1,629 | 6,500 | 4,971 | Efficiency through guided convergence |
| **Total Wall-Clock Time** | 131.8s | 298.1s | 635.5s | DDIV includes multi-agent verification & network |
| **Mean Latency / Task** | 14.6s | 33.1s | 70.6s | Comprehensive verification tradeoff |
| **Cloud Token Cost ($)** | $0.00 | $0.00 | $0.00 | Free tiers utilized (0 paid calls) |

---

## 4. Per-Task 3-Way Comparative Matrix

| Program Name | `BASELINE` (Local) | `RETRY_ONLY` (Local) | `FULL_DDIV` (Option A) | Dominant Outcome |
| :--- | :--- | :--- | :--- | :---: |
| [`bitcount`](file:///d:/PROJECTS/DDIV/python_programs/bitcount.py) | **FAIL** (att=1, 1,471t, 16.3s)<br/>*Empty patch / no modification* | **FAIL** (att=3, 4,459t, 14.8s)<br/>*Empty patch across all 3 atts* | **PASS** (att=1, 3,110t, 37.1s)<br/>*Bitwise operator fixed: `n &= n - 1`* | **FULL_DDIV Only** |
| [`depth_first_search`](file:///d:/PROJECTS/DDIV/python_programs/depth_first_search.py) | **FAIL** (att=1, 1,594t, 9.5s)<br/>*Python AST indent error* | **FAIL** (att=3, 4,795t, 25.5s)<br/>*AST indent error & empty diff* | **FAIL** (att=3, 13,273t, 128.1s)<br/>*Recursion cycle assertion failure* | **Unresolved Cohort** |
| [`detect_cycle`](file:///d:/PROJECTS/DDIV/python_programs/detect_cycle.py) | **FAIL** (att=1, 1,570t, 12.5s)<br/>*1 test failed assertion* | **FAIL** (att=3, 5,692t, 35.2s)<br/>*2 tests failed assertion* | **PASS** (att=1, 4,771t, 49.3s)<br/>*Guard added: `hare is None or ...`* | **FULL_DDIV Only** |
| [`find_in_sorted`](file:///d:/PROJECTS/DDIV/python_programs/find_in_sorted.py) | **FAIL** (att=1, 1,645t, 12.6s)<br/>*1 test failed assertion* | **FAIL** (att=3, 8,863t, 41.9s)<br/>*1 test failed assertion* | **PASS** (att=1, 3,377t, 48.7s)<br/>*Inclusive bounds: `binsearch(mid + 1, end)`* | **FULL_DDIV Only** |
| [`gcd`](file:///d:/PROJECTS/DDIV/python_programs/gcd.py) | **FAIL** (att=1, 1,479t, 5.8s)<br/>*Empty patch / no modification* | **FAIL** (att=3, 4,479t, 16.0s)<br/>*Empty patch across all 3 atts* | **PASS** (att=1, 2,836t, 45.9s)<br/>*Euclidean step: `gcd(b, a % b)`* | **FULL_DDIV Only** |
| [`get_factors`](file:///d:/PROJECTS/DDIV/python_programs/get_factors.py) | **FAIL** (att=1, 1,607t, 12.7s)<br/>*1 test failed assertion* | **FAIL** (att=3, 7,647t, 39.5s)<br/>*1 test failed assertion* | **FAIL** (att=3, 6,955t, 77.6s)<br/>*Ambiguous anchor in factor loop* | **Unresolved Cohort** |
| [`hanoi`](file:///d:/PROJECTS/DDIV/python_programs/hanoi.py) | **FAIL** (att=1, 1,763t, 13.1s)<br/>*1 test failed assertion* | **FAIL** (att=3, 6,890t, 41.0s)<br/>*Empty patch on final attempt* | **PASS** (att=1, 3,408t, 49.7s)<br/>*Peg tuple: `steps.append((start, end))`* | **FULL_DDIV Only** |
| [`kheapsort`](file:///d:/PROJECTS/DDIV/python_programs/kheapsort.py) | **FAIL** (att=1, 1,775t, 14.3s)<br/>*1 test failed assertion* | **FAIL** (att=3, 6,630t, 41.6s)<br/>*AST indent error & missing anchor* | **PASS** (att=1, 3,490t, 59.5s)<br/>*Slice stream: `for x in arr[k:]:`* | **FULL_DDIV Only** |
| [`knapsack`](file:///d:/PROJECTS/DDIV/python_programs/knapsack.py) | **FAIL** (att=1, 1,758t, 34.9s)<br/>*15.0s Execution timeout* | **FAIL** (att=3, 9,048t, 42.7s)<br/>*Missing anchor string across atts* | **PASS** (att=1, 3,519t, 139.5s)<br/>*Capacity condition: `weight <= j`* | **FULL_DDIV Only** |

---

## 5. Failure Mode Taxonomy & Distribution Analysis

```mermaid
pie title Failure Modes across All Failed Attempts (RETRY_ONLY vs FULL_DDIV)
    "Assertion / Logic Error" : 16
    "No Modification Extracted" : 8
    "Syntax / Indent AST Error" : 3
    "Missing / Ambiguous Anchor" : 6
```

### Breakdown by Condition

| Failure Classification | `BASELINE` (9 atts) | `RETRY_ONLY` (27 atts) | `FULL_DDIV` (13 atts) | Root Cause & Behavioral Analysis |
| :--- | :---: | :---: | :---: | :--- |
| **Logic / Assertion Failure** | 5 (55.6%) | 13 (48.1%) | 3 (23.1%) | Model produced incorrect algorithm logic; failed pytest assertions |
| **No Modification Extracted** | 2 (22.2%) | 8 (29.6%) | 0 (0.0%) | Local model emitted passive text or restated bug without diff modifications |
| **Syntax / AST Indentation Error**| 1 (11.1%) | 3 (11.1%) | 0 (0.0%) | Unsupervised coder output malformed indentation or invalid Python grammar |
| **Missing / Ambiguous Anchor** | 0 (0.0%) | 3 (11.1%) | 3 (23.1%) | Target anchor string could not be uniquely located in source file |
| **Execution Timeout (15s limit)** | 1 (11.1%) | 0 (0.0%) | 0 (0.0%) | Infinite recursion or unconstrained loop in candidate patch |
| **Successfully Resolved** | 0 (0.0%) | 0 (0.0%) | **7 (53.8%)** | All tests passed and patch verified |

> [!TIP]
> **Why `RETRY_ONLY` Fails to Converge:**  
> When a small local model (`qwen2.5-coder:7b`) receives raw pytest tracebacks like `AssertionError: assert [1, 2] == [2, 1]`, it typically makes local edits near the assert without grasping algorithm invariants. Furthermore, after an initial failure, it often suffers from "prompt confusion," producing empty diffs or failing to anchor lines correctly. The DDIV Supervisor eliminates this pathology by providing a clean natural-language plan with architectural context before the coder generates code.

---

## 6. Token & Resource Ledger Analysis

```mermaid
%%{init: {'theme': 'neutral'}}%%
graph TD
    subgraph Token Allocation by Condition
        TB["BASELINE: 14,662 Tokens<br/>(100% Local Ollama)"]
        TR["RETRY_ONLY: 58,503 Tokens<br/>(100% Local Ollama)"]
        TF["FULL_DDIV: 44,739 Tokens<br/>(62% Ollama, 24% Groq, 14% Gemini)"]
    end
```

### Provider & Role Decomposition for Batch 1

| Condition | Provider | Model | Role | Prompt Tokens | Completion Tokens | Total Tokens | % of Condition Tokens |
| :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: |
| **`BASELINE`** | Ollama | `qwen2.5-coder:7b` | Coder | 13,806 | 856 | 14,662 | 100.0% |
| **`RETRY_ONLY`**| Ollama | `qwen2.5-coder:7b` | Coder | 55,940 | 2,563 | 58,503 | 100.0% |
| **`FULL_DDIV`** | Gemini | `gemini-3.1-flash-lite`| Locator | 5,690 | 494 | 6,184 | 13.8% |
| | Groq | `qwen/qwen3.8-27b` | Supervisor | 2,544 | 339 | 2,883 | 6.4% |
| | Groq | `qwen/qwen3.8-27b` | Tester | 7,105 | 684 | 7,789 | 17.4% |
| | Ollama | `qwen2.5-coder:7b` | Coder | 26,458 | 1,425 | 27,883 | 62.3% |
| | **Totals (DDIV)** | | | **41,797** | **2,942** | **44,739** | **100.0%** |

### Quota Ledger Status as of Batch 1 Completion
- **Today's Groq Consumption:** `0` tokens billed today (reused Batch 1). Remaining: **100,000 / 100,000 (100.0%)**.
- **Today's Gemini Consumption:** `0` tokens billed today (reused Batch 1). Remaining: **30,000 / 30,000 (100.0%)**.
- **Production Database Integrity:** `data/ddiv_memory.db` remains pristine with zero QuixBugs records.

---

## 7. Patch Gallery: The 7 Canonical FULL_DDIV Repairs

Below are the surgical, minimal patches synthesized by `FULL_DDIV` that passed 100% of specification test suites:

### 1. `bitcount` (Brian Kernighan's Bit Manipulation)
```diff
--- a/python_programs/bitcount.py
+++ b/python_programs/bitcount.py
@@ -2,7 +2,7 @@
 def bitcount(n):
     count = 0
     while n:
-        n ^= n - 1
+        n &= n - 1
         count += 1
     return count
```

### 2. `detect_cycle` (Floyd's Cycle-Finding Algorithm)
```diff
--- a/python_programs/detect_cycle.py
+++ b/python_programs/detect_cycle.py
@@ -2,7 +2,7 @@
     hare = tortoise = node
 
     while True:
-        if hare.successor is None:
+        if hare is None or hare.successor is None:
             return False
 
         tortoise = tortoise.successor
```

### 3. `find_in_sorted` (Binary Search Upper-Bound Inclusion)
```diff
--- a/python_programs/find_in_sorted.py
+++ b/python_programs/find_in_sorted.py
@@ -6,7 +6,7 @@
         if x < arr[mid]:
             return binsearch(start, mid)
         elif x > arr[mid]:
-            return binsearch(mid, end)
+            return binsearch(mid + 1, end)
         else:
             return mid
```

### 4. `gcd` (Euclidean Algorithm State Step)
```diff
--- a/python_programs/gcd.py
+++ b/python_programs/gcd.py
@@ -2,7 +2,7 @@
     if b == 0:
         return a
     else:
-        return gcd(a % b, b)
+        return gcd(b, a % b)
```

### 5. `hanoi` (Tower of Hanoi Peg Tuple Ordering)
```diff
--- a/python_programs/hanoi.py
+++ b/python_programs/hanoi.py
@@ -3,7 +3,7 @@
     if height > 0:
         helper = ({1, 2, 3} - {start} - {end}).pop()
         steps.extend(hanoi(height - 1, start, helper))
-        steps.append((start, helper))
+        steps.append((start, end))
         steps.extend(hanoi(height - 1, helper, end))
 
     return steps
```

### 6. `kheapsort` (K-Sorted Array Min-Heap Generator)
```diff
--- a/python_programs/kheapsort.py
+++ b/python_programs/kheapsort.py
@@ -4,7 +4,7 @@
     heap = arr[:k]
     heapq.heapify(heap)
 
-    for x in arr:
+    for x in arr[k:]:
         yield heapq.heappushpop(heap, x)
 
     while heap:
```

### 7. `knapsack` (Dynamic Programming Capacity Boundary)
```diff
--- a/python_programs/knapsack.py
+++ b/python_programs/knapsack.py
@@ -9,7 +9,7 @@
         for j in range(1, capacity + 1):
             memo[i, j] = memo[i - 1, j]
 
-            if weight < j:
+            if weight <= j:
                 memo[i, j] = max(
                     memo[i, j],
                     value + memo[i - 1, j - weight]
```

---

## 8. Multi-Batch Consolidation Specification

To ensure seamless merging with **Batch 2 (Tasks 10–18)** and **Batch 3 (Tasks 19–27)**, this report adheres to the following unification schema:

```
Consolidated Report Format:
├── Header & Global Benchmark Objectives
├── Global 3-Condition Aggregate Table (27 Tasks Total)
│   ├── Baseline (27 tasks, N resolved, % rate, total tokens, total latency)
│   ├── Retry-Only (27 tasks, N resolved, % rate, total tokens, total latency)
│   └── Full-DDIV (27 tasks, N resolved, % rate, total tokens, total latency)
├── Batch-by-Batch Comparative Breakdown
│   ├── Batch 1 (Tasks 1–9)  <-- [Embedded from this report]
│   ├── Batch 2 (Tasks 10–18) <-- [To be populated after Batch 2 execution]
│   └── Batch 3 (Tasks 19–27) <-- [To be populated after Batch 3 execution]
├── Comprehensive 27-Task Master Matrix (Tasks 1 to 27)
├── Cross-Batch Failure Taxonomy & Error Distribution
├── Global Efficiency & Quota Ledger Analysis
└── Final Scientific Conclusion on Multi-Agent Supervision vs Local Retries
```

All metrics from this batch are archived in machine-readable JSON format at [`results/quixbugs_three_condition_eval_20261016T120000Z/batch_1_detailed_metrics.json`](file:///d:/PROJECTS/DDIV/results/quixbugs_three_condition_eval_20261016T120000Z/batch_1_detailed_metrics.json) for automatic cross-batch aggregation scripts.
