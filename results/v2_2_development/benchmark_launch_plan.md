# DDIV v2.2 Controlled 20-Task Evaluation Launch Plan

**Evaluation Framework:** DDIV v2.2 Frozen Benchmark  
**Total Tasks:** 20 distinct SWE-bench Verified tasks across 9 diverse Python repositories  
**Conditions per Task:** 3 (`BASELINE`, `RETRY_ONLY`, `FULL_DDIV`)  
**Total Planned Runs:** 60 runs  
**Status:** **PENDING USER EXPLICIT APPROVAL (DO NOT LAUNCH AUTOMATICALLY)**  

---

## 1. Experimental Conditions & Design

Each task will be evaluated under identical repository states, identical base commits, and identical evaluation environments across three conditions:

1. **`BASELINE` (1 attempt):** Single repair attempt without diagnosis, test understanding, or supervisor recovery.
2. **`RETRY_ONLY` (up to 3 attempts):** Up to three blind retry attempts from clean workspace states without diagnosis or supervisor feedback.
3. **`FULL_DDIV` (up to 3 attempts):** Full multi-agent orchestration featuring:
   - Root Cause Analysis (`TestUnderstandingAgent`)
   - Syntax-verified, block-aware patch synthesis (`DemoPatchBuilder`)
   - Prompt-constrained localization (`OllamaCoderModelProvider`)
   - Non-blocking patch criticism (`PatchCriticAgent`)
   - Objective failure disambiguation (`FailureDisambiguator`)
   - Anti-repetition negative constraints (`ProposalHistory`)
   - Closed-loop supervisor recovery (`SupervisorAgent`)

---

## 2. Model & Provider Routing

| Role | Model | Provider | Quota Dependence |
| :--- | :--- | :--- | :--- |
| **Coder (Treatment)** | `qwen2.5-coder:7b` | Local Ollama (`http://localhost:11434`) | **Quota-Free (Local GPU/CPU inference)** |
| **Locator** | `gemini-3.1-flash-lite` | Google Cloud API | Cloud API (Low token count per call) |
| **Test Understanding** | `qwen/qwen3.8-27b` | Groq API | Cloud API (~15k tokens / run) |
| **Supervisor** | `qwen/qwen3.8-27b` | Groq API | Cloud API (~12k tokens / run) |
| **Patch Critic** | `qwen/qwen3.8-27b` | Groq API | Cloud API (~8k tokens / run) |
| **Tester** | `qwen/qwen3.8-27b` | Groq API | Cloud API (~5k tokens / run) |

> [!IMPORTANT]
> **Strict Zero-Fallback Policy:** When Ollama is configured, any timeout or failure in the local model halts that attempt immediately and is recorded as an error. Under no circumstances will inference silently switch to a cloud provider.

---

## 3. Batch Partitioning & Staging Matrix (60 Runs Total)

The evaluation is partitioned into 7 sequential batches to ensure strict resource tracking and allow checkpointing between batches:

| Batch | Tasks Included | Repo Distribution | Runs (3 cond) | Projected Cloud Quota |
| :---: | :--- | :--- | :---: | :---: |
| **1** | `pylint-dev__pylint-6903`<br>`mwaskom__seaborn-3187`<br>`pydata__xarray-7393` | pylint, seaborn, xarray | 9 | ~114,321 tokens |
| **2** | `astropy__astropy-8872`<br>`astropy__astropy-14508`<br>`psf__requests-2931` | astropy, requests | 9 | ~114,321 tokens |
| **3** | `pytest-dev__pytest-8399`<br>`sympy__sympy-23413`<br>`matplotlib__matplotlib-26342` | pytest, sympy, matplotlib | 9 | ~114,321 tokens |
| **4** | `scikit-learn__scikit-learn-26323`<br>`pydata__xarray-4966`<br>`pylint-dev__pylint-4970` | scikit-learn, xarray, pylint | 9 | ~114,321 tokens |
| **5** | `sympy__sympy-13878`<br>`django__django-16429`<br>`sphinx-doc__sphinx-8638` | sympy, django, sphinx | 9 | ~114,321 tokens |
| **6** | `django__django-11141`<br>`pytest-dev__pytest-7982`<br>`scikit-learn__scikit-learn-13496` | django, pytest, scikit-learn | 9 | ~114,321 tokens |
| **7** | `sphinx-doc__sphinx-8269`<br>`matplotlib__matplotlib-20676` | sphinx, matplotlib | 6 | ~76,214 tokens |
| **TOTAL** | **20 distinct tasks** | **9 repositories** | **60 runs** | **Quota-budgeted** |

---

## 4. Execution Protocol & Verification Gates

Prior to dispatching any batch:
1. **Pre-Launch Gate Check:** Must pass `python scripts/launch_gate_check.py --batch N`.
2. **Local Ollama Readiness:** Verify `qwen2.5-coder:7b` is loaded and responding to `/api/generate`.
3. **Workspace Isolation:** All workspaces isolated under `data/workspaces/benchmark_v2_2/batch_{N}/`.
4. **Historical Immutability:** Historical results under `results/local_ollama_coder/` and `results/demo_reproduction/` remain strictly read-only.
5. **No Blind Runs:** Execution pauses between batches to monitor rate limits and disk space.
