# Report D: Mechanism Audit (Memory, Trust, Recovery)

## 1. Episodic Memory Mechanism
- **Seed Database:** `11` records preloaded from non-target historical repositories.
- **Zero Contamination Verification:** Audit confirmed 0 records from `pylint-6903`, `pylint-4970`, `sympy-23413`, or `seaborn-3187`.
- **Condition Isolation:** `BASELINE` and `RETRY_ONLY` made 0 memory calls. `FULL_DDIV` accessed the isolated memory store.

## 2. Recovery & Anti-Repetition Mechanism
- **`ProposalHistory` Operation:** Failed candidate edits were hashed and recorded across retry attempts.
- **Negative Constraint Directives:** Coder prompts in attempt $\ge 2$ received explicit `DO NOT REPEAT PREVIOUS FAILED PROPOSALS` directives.
- **`FailureDisambiguator`:** Provided empirical counts of F2P/P2P pass/fail states without revealing gold patch content.

## 3. Trust Ledger & Low-Trust Critique
- **Ledger Isolation:** Trust states were initialized cleanly per condition run.
- **Critique Invocations:** AST and unified diff syntax critique gates checked candidate patches prior to repository application.