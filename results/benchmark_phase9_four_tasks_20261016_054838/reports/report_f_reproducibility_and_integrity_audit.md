# Report F: Reproducibility, Workspace Isolation, and Integrity Audit

## 1. Workspace Isolation Verification
- **Fail-Closed Isolation Gates:** `verify_workspace_isolation` checked that each workspace had its own `.git`, resolved to its own top-level directory, and matched the exact base commit.
- **Git Ceiling Verification:** `GIT_CEILING_DIRECTORIES=D:\DDIV` strictly blocked git operations from traversing up to the master repository.

## 2. Integrity Checks & Anti-Contamination Verification
- **Target Task Exclusion:** Confirmed 0 target task records in seeded memory database.
- **No Leaked Reference Patches:** Reference gold patches and test patches were never exposed to Coder or Locator agents.
- **Evaluator Scope:** Evaluated exclusively via internal targeted evaluator (`InternalSWEBenchEvaluator`). Never claimed official SWE-bench evaluation harness.

## 3. Environment Specifications
- **Master Commit HEAD:** `68ebe921971a8d8ba6e5611a927eefd055b3c96f`
- **Python Runtime:** Python 3.11 Windows 64-bit
- **Local Coder:** Ollama `qwen2.5-coder:7b` (localhost:11434)
- **Supporting Agent APIs:** Groq (`qwen/qwen3.8-27b`), Google Gemini (`gemini-3.1-flash-lite`)