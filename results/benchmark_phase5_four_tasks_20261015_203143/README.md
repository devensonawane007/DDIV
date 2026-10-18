# DDIV Phase 5 Benchmark: Four-Task Controlled Benchmark

This directory contains the complete execution results, logs, captured prompts, and comprehensive audit reports for DDIV Phase 5.

## Directory Structure
- `reports/`: Markdown audit reports (Reports A-F) and machine-readable deliverables (`benchmark_manifest.json`, `run_results.jsonl`, `parameter_audit.csv`, `task_summary.csv`, `mechanism_audit.json`, `artifact_index.json`).
- `results/`: Per-job JSON result records and candidate diff patches.
- `logs/`: Full console execution logs for each of the 12 benchmark runs.
- `prompts/`: Verbatim captured LLM prompts across Locator, Coder, and Supervisor.
- `memory/`: Seed manifest and isolated SQLite memory database (`phase5_memory_ddiv.db`).
- `workspaces/`: Pristine isolated working directories for each executed task/condition.