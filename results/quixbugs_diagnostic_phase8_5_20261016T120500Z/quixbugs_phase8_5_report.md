# DDIV Phase 8.5: Targeted QuixBugs Diagnostic Repair Report

**Execution Timestamp:** 2026-10-16T06:39:14Z  
**Model:** `qwen2.5-coder:7b` via local Ollama (`http://localhost:11434`)  
**Total Tasks:** 2 (Targeted persistent failures: quicksort, rpn_eval)  
**Total Runs:** 6  
**Total Wall-Clock Time:** 223.26s  
**Cost:** $0.00 (100% local inference, zero cloud APIs)  

---

## Summary of Experimental Conditions

| Condition | Resolved | Resolution Rate | Total Tokens | Wall-Clock Duration |
| :--- | :---: | :---: | :---: | :---: |
| **`BASELINE`** (1 attempt, T=0.0) | 0 / 2 | 0.0% | 3,590 | 44.25s |
| **`RETRY_ONLY`** (up to 3 att, T=0.0/0.2, prior-patch diff) | 0 / 2 | 0.0% | 12,188 | 81.46s |
| **`FULL_DDIV`** (up to 3 att, T=0.0/0.2, supervisor, anti-repetition, memory) | 0 / 2 | 0.0% | 12,504 | 91.95s |

---

## Diagnostic Task Details

### `quicksort`

| Condition | Resolved | Attempts | Tokens | Duration | Final Verdict |
| :--- | :---: | :---: | :---: | :---: | :--- |
| `BASELINE` | **FAILED** | 1 | 1,774 | 32.08s | UNRESOLVED (Tests failed) |
| `RETRY_ONLY` | **FAILED** | 3 | 6,645 | 49.16s | UNRESOLVED (Tests failed) |
| `FULL_DDIV` | **FAILED** | 3 | 6,956 | 58.28s | UNRESOLVED (Tests failed) |

### `rpn_eval`

| Condition | Resolved | Attempts | Tokens | Duration | Final Verdict |
| :--- | :---: | :---: | :---: | :---: | :--- |
| `BASELINE` | **FAILED** | 1 | 1,816 | 12.16s | PatchBuilder failed: Anchor ambiguous in 'python_programs/rpn_eval.py' (2 matches). (category: ANCHOR_AMBIGUOUS) |
| `RETRY_ONLY` | **FAILED** | 3 | 5,543 | 32.30s | PatchBuilder failed: Anchor ambiguous in 'python_programs/rpn_eval.py' (2 matches). (category: ANCHOR_AMBIGUOUS) |
| `FULL_DDIV` | **FAILED** | 3 | 5,548 | 33.67s | PatchBuilder failed: Anchor ambiguous in 'python_programs/rpn_eval.py' (2 matches). (category: ANCHOR_AMBIGUOUS) |
