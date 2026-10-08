# DDIV v2.1 Immutable Implementation Checkpoint

- **DDIV Version**: 2.1
- **Code Commit Hash**: `f863d0438886059b42072e18f6fcc5c770b9b85e` (`f863d04`)
- **Dataset**: SWE-bench Verified (`data/swebench/test-00000-of-00001.parquet`)
- **Benchmark Manifest**: `data/experiments/benchmark_v2_tasks.json`
- **Experimental Conditions & Budgets**:
  - `BASELINE`: 1 attempt (Single pass, feedforward, supervisor/memory/trust disabled)
  - `RETRY_ONLY`: Up to 3 attempts (Blind retry from clean state, supervisor/memory/trust disabled)
  - `FULL_DDIV`: Up to 3 attempts (Full Detect $\to$ Diagnose $\to$ Intervene $\to$ Verify closed loop with RCA, critic, memory, trust)
- **Model Infrastructure**:
  - **Locator**: `gemini` (`gemini-3.1-flash-lite`)
  - **Coder**: `groq` (`openai/gpt-oss-120b`)
  - **Tester**: `groq` (`qwen/qwen3.8-27b`)
  - **Supervisor**: `groq` (`qwen/qwen3.8-27b`)
  - **TestUnderstanding (RCA)**: `groq` (`qwen/qwen3.8-27b`)
  - **PatchCritic**: `groq` (`qwen/qwen3.8-27b`)
- **Frozen Trust Deltas**:
  - Success: `+0.05`
  - Failure: `-0.08`
  - Regression: `-0.10`

> **Note**: This checkpoint is frozen. No behavioral or code modifications occur after this point.
