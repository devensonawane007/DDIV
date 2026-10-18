# DDIV Phase 8.5: Targeted QuixBugs Diagnostic Repair Report

**Execution Timestamp:** 2026-10-16T06:44:20Z  
**Model:** `qwen2.5-coder:7b` via local Ollama (`http://localhost:11434`)  
**Total Tasks:** 2 (Targeted persistent failures: quicksort, rpn_eval)  
**Total Runs:** 6  
**Total Wall-Clock Time:** 140.75s  
**Cost:** $0.00 (100% local inference, zero cloud APIs)  

---

## Summary of Experimental Conditions

| Condition | Resolved | Resolution Rate | Total Tokens | Wall-Clock Duration |
| :--- | :---: | :---: | :---: | :---: |
| **`BASELINE`** (1 attempt, T=0.0) | 1 / 2 | 50.0% | 3,570 | 30.05s |
| **`RETRY_ONLY`** (up to 3 att, T=0.0/0.2, prior-patch diff) | 1 / 2 | 50.0% | 8,488 | 65.84s |
| **`FULL_DDIV`** (up to 3 att, T=0.0/0.2, supervisor, anti-repetition, memory) | 2 / 2 | 100.0% | 6,027 | 41.34s |

---

## Diagnostic Task Details

### `quicksort`

| Condition | Resolved | Attempts | Tokens | Duration | Final Verdict |
| :--- | :---: | :---: | :---: | :---: | :--- |
| `BASELINE` | **FAILED** | 1 | 1,754 | 18.64s | UNRESOLVED (Tests failed) |
| `RETRY_ONLY` | **FAILED** | 3 | 6,672 | 54.74s | UNRESOLVED (Tests failed) |
| `FULL_DDIV` | **RESOLVED** | 2 | 4,211 | 30.07s | RESOLVED |

### `rpn_eval`

| Condition | Resolved | Attempts | Tokens | Duration | Final Verdict |
| :--- | :---: | :---: | :---: | :---: | :--- |
| `BASELINE` | **RESOLVED** | 1 | 1,816 | 11.41s | RESOLVED |
| `RETRY_ONLY` | **RESOLVED** | 1 | 1,816 | 11.10s | RESOLVED |
| `FULL_DDIV` | **RESOLVED** | 1 | 1,816 | 11.28s | RESOLVED |
