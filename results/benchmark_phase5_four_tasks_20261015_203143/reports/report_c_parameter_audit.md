# Report C: Parameter Audit and Sensitivity Analysis

## 1. Frozen Parameter Configuration Table

| Parameter Name | Frozen Value | Configuration Scope | Actuation Mechanism | Empirical Observation |
| :--- | :---: | :--- | :--- | :--- |
| `max_attempts` (Baseline) | `1` | Per-job worker | Hard loop termination after attempt 1 | Verified: exactly 1 attempt executed |
| `max_attempts` (Retry / Full) | `3` | Per-job worker | Retry loop up to 3 attempts | Verified: jobs executed 1 to 3 attempts |
| `coder_trust_critique_threshold` | `0.70` | Supervisor / Acceptance | Rejects candidate patch on low trust unless critique passes | Tested and verified offline & online |
| `coder_temperature` | `0.2` | Coder LLM adapter | Ollama generation temperature | Deterministic low-temperature sampling |
| `trust_decay_rate` | `0.05` | TrustLedger | Decrements trust upon verification failure | Trust updates recorded in ledger |
| `memory_top_k` | `3` | MemoryRetriever | Limits retrieved experiences to top 3 | Injected at most 3 matched experiences |
| `memory_similarity_threshold` | `0.65` | MemoryRetriever | Min similarity score cutoff | Excluded irrelevant experiences |

## 2. Sensitivity Analysis & Discussion
- **Attempt Budget ($K \in \{1, 3\}$):** Multi-attempt capability allows recovering from early syntax/anchoring errors without human intervention.
- **Critique Threshold (0.70):** Low-trust critique adds an automated static verification safety barrier before test execution.
- **Coder Temperature (0.2):** Keeps code generation tightly anchored to verbatim source lines while maintaining flexibility for multi-line edits.