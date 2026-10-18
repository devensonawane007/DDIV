# DDIV Phase 8.8: Cloud Resource, Latency, and Cost Preflight Estimate

## 1. Experimental Cohort Scope
- **Target Cohort:** 27 QuixBugs tasks unresolved by local `FULL_DDIV`.
- **Maximum Attempts per Task:** 3 attempts.
- **Maximum Invocations per Task:** Up to 3 Locator calls, 3 Coder calls, 3 Tester calls, and 2-3 Supervisor calls.
- **Maximum Evaluated Attempts:** **81 attempts** (fewer if tasks resolve on Attempt 1 or 2).

---

## 2. Token Projections & API Pricing Assumptions

### Projected Invocations and Token Volumes (Upper Bound: 81 Attempts)

| Agent Role | Model & Provider | Estimated Calls | Mean Prompt Tok / Call | Mean Compl Tok / Call | Total Prompt Tokens | Total Compl Tokens | Total Tokens |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Locator** | `gemini-3.1-flash-lite` (Google) | 27–81 | 1,500 | 150 | 40,500 – 121,500 | 4,050 – 12,150 | ~133,650 |
| **Supervisor** | `qwen/qwen3.8-27b` (Groq) | 27–54 | 2,200 | 200 | 59,400 – 118,800 | 5,400 – 10,800 | ~129,600 |
| **Tester** | `qwen/qwen3.8-27b` (Groq) | 27–81 | 1,600 | 250 | 43,200 – 129,600 | 6,750 – 20,250 | ~149,850 |
| **Coder (Local Option)** | `qwen2.5-coder:7b` (Ollama) | 27–81 | 2,100 | 150 | 56,700 – 170,100 | 4,050 – 12,150 | ~182,250 |
| **Coder (Cloud Option)** | `openai/gpt-oss-120b` (Groq) | 27–81 | 2,100 | 150 | 56,700 – 170,100 | 4,050 – 12,150 | ~182,250 |

---

## 3. Financial Cost Breakdown

### Pricing Tiers (Standard Public Rates)
- **Google Gemini 1.5/2.0 Flash-Lite:**
  - Prompt: $0.075 per 1,000,000 tokens ($0.000075 / 1k tokens)
  - Completion: $0.300 per 1,000,000 tokens ($0.000300 / 1k tokens)
  - Estimated Locator Cost: $(121.5 \times 0.000075) + (12.15 \times 0.0003) = \mathbf{\$0.013}$
- **Groq Cloud API (Qwen 2.5 32B / 72B / gpt-oss):**
  - Developer Free Tier: 30 Requests/Min, 6,000 Tokens/Min (Cost = **$0.00**)
  - Standard Pay-As-You-Go: ~$0.05 – $0.59 per 1M tokens
  - Maximum Estimated Groq Cost (Paid): ~280k tokens @ $0.20/1M = **$0.056**
- **Local Ollama Coder:**
  - Cost = **$0.00** (Local inference on GPU)

### Total Estimated Financial Expense
- **Option A (Hybrid: Local Coder + Cloud Multi-Agent):** **< $0.10 total** (or **$0.00** within free tier quotas).
- **Option B (Full Cloud: Cloud Coder + Cloud Multi-Agent):** **< $0.25 total**.

---

## 4. Wall-Clock Latency Projections
- Mean latency per multi-agent attempt: ~15.0 – 20.0 seconds.
- Total estimated duration for 81 attempts: **~1,200 – 1,600 seconds (~20 – 27 minutes)**.
- Request timeouts: 120s for cloud agents, 240s for local Coder.
- Pytest execution timeout: strictly enforced at 15.0s per attempt.
