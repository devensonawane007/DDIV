# Report E: Comparative Analysis Across Conditions

## 1. Metric Comparison Across Protocol Conditions

| Metric | BASELINE | RETRY_ONLY | FULL_DDIV |
| :--- | :---: | :---: | :---: |
| Tasks Evaluated | 4 | 4 | 4 |
| Resolved Count | 0/4 | 0/4 | 0/4 |
| Resolution Rate | 0.0% | 0.0% | 0.0% |
| Total Attempts Executed | 4 | 12 | 12 |
| Mean Duration / Job | 209.5s | 358.0s | 433.4s |
| Total Tokens Consumed | 35,560 | 108,350 | 158,979 |

## 2. Qualitative Differences & Trade-Offs
- **`BASELINE` vs. `RETRY_ONLY`:** Single-attempt baseline fails completely when initial anchor line has minor whitespace or character mismatch. Multi-attempt retry allows the agent to self-correct.
- **`RETRY_ONLY` vs. `FULL_DDIV`:** `FULL_DDIV` adds structural supervisor analysis, failure diagnosis (F1-F6), and historical memory references, trading runtime for targeted guidance.