# DDIV Phase 8.9: Cloud-Assisted Multi-Agent Repair Protocol (QuixBugs 27 Unresolved Tasks)

## 1. Scientific Objective
Empirically evaluate whether the full multi-agent DDIV architecture (incorporating cloud-based Locator, Supervisor, and Tester agents) can successfully diagnose and repair the **27 hard QuixBugs defects** that the local single-model `FULL_DDIV` configuration failed to resolve in Phase 8.6.

---

## 2. Experimental Controls and Baseline Comparison
- **Target Cohort:** Exactly the 27 QuixBugs tasks identified in `unresolved_task_manifest.json`.
- **Baseline Comparator:** Local `FULL_DDIV` (3 attempts, $T=0.0 \to 0.2$, local Qwen 2.5 Coder 7B).
- **Evaluation Criteria:**
  - Primary: Binary task resolution (100% specification tests pass).
  - Secondary: Multi-attempt recovery rate, patch syntax validity, patch application rate, token efficiency, latency, and financial cost.

---

## 3. Strict Ground-Truth Isolation & Safety Rules
1. **Zero Ground-Truth Leaks:** Model-facing agent workspaces contain exclusively `python_programs/<name>.py`.
2. **Hidden Test Suites:** All test fixtures, expected JSON inputs/outputs, and reference solutions remain strictly outside the agent workspace in temporary out-of-process pytest sandboxes.
3. **Pristine State Protection:**
   - Production memory (`data/ddiv_memory.db`) remains completely untouched.
   - All experiment memory records must be written to an isolated SQLite file: `quixbugs_cloud_assisted_memory.db`.
   - Historical Phase 8.6 and 8.7 directories remain frozen.
4. **False-Success Gates:** Empty diffs, non-compiling AST syntax, and non-target file edits fail-closed before execution.
5. **Timeout Enforcement:** Subprocess pytest executions are strictly killed after 15.0 seconds.

---

## 4. Verification and Execution Gates
- Gate 1: Workspace verification (no test files present).
- Gate 2: Cloud credential check (confirm API keys loaded without leaking).
- Gate 3: AST patch validation gate active.
- Gate 4: Anti-repetition gate active.
- Gate 5: Isolated memory storage active.
