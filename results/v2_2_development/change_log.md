# DDIV v2.2 Architecture & Implementation Change Log

**Release Target:** DDIV v2.2  
**Timestamp:** 2026-10-13  
**Status:** Implemented & Verified in Isolated Components  

---

## 1. Architectural Integrity & Isolation Guarantees

In strict adherence to project research protocols:
- **Frozen Directories Untouched:** Zero modifications made to `agents/`, `recovery/`, `evaluation/`, `memory/`, and `models/`. `git status --porcelain agents recovery evaluation memory models` reports **0 diff lines**.
- **Historical Artefacts Preserved:** All historical results (`results/demo_reproduction/`, `results/fair_comparison_pylint6903/`, `results/local_ollama_coder/`), frozen checkpoint (`data/experiments/benchmark_v2_1/checkpoint.json`), and benchmark manifest (`data/experiments/benchmark_v2_tasks.json`) remain cryptographically identical to their frozen state.
- **Provider Isolation:** Default Coder provider remains Groq; local Ollama (`qwen2.5-coder:7b`) is invoked only when explicitly configured (`DDIV_CODER_PROVIDER=ollama`) with zero silent cloud fallback.

---

## 2. Empirical Failure Modes & Targeted Implementations

Based on the empirical audit of 20 attempts across 9 runs in the local Ollama pilot (`results/v2_2_development/failure_analysis.md`), four specific failure modes were addressed through isolated v2.2 components:

### Component 1: `scripts/demo_patch_builder.py` (Block-Aware Indentation & Path Remapping)
- **Motivation (Failure Mode B - Indentation & Block Scope Corruption):**
  - In `pylint-4970` and `pylint-6903`, the 7B model generated unindented code or code indented relative to line prefixes that did not account for block nesting (e.g. inserting into `def process_module(self, node):` at the class body level or misaligned `insert_after`).
- **Implementation:**
  - Added `normalize_code_indentation(code: str, target_indent: int)`: calculates correct indentation level by inspecting anchor line keywords (`def`, `class`, `if`, `for`, `while`, `try`, `with`, `elif`, `else`, `except`, `finally`). If the operation is `insert_after` following a block header ending with `:`, the target indentation is automatically indented by +4 spaces.
  - Stripped leading blank lines from incoming code proposals before calculating indentation to prevent leading newline alignment skew.
  - Enhanced `anchor_indent` computation: accounts for leading whitespace inside the anchor string itself (`len(line_prefix) + (len(anchor) - len(anchor.lstrip(" ")))`).
- **Motivation (Failure Mode A - Model Placeholder Hallucination):**
  - In `pylint-4970`, Coder generated paths like `path/to/file.py` and `path/to/similar_checker.py`.
- **Implementation:**
  - Added `safe_resolve_target_file(raw_path: str, workspace_root: Path)`: if a path contains placeholder segments (`path/to/` or `.../`), it scans the workspace for files with the identical base filename. If and only if exactly **one** matching file exists in the repository, it safely remaps the path to that verified file. If zero or more than one file matches (such as ambiguous or non-existent files), the modification is cleanly rejected with `FILE_NOT_FOUND`.

### Component 2: `scripts/ollama_coder_adapter.py` (Constrained File Path Instruction)
- **Motivation (Failure Mode A):**
  - The 7B model occasionally mirrors prompt example formatting (`path/to/...`) instead of adhering to localized file paths.
- **Implementation:**
  - Enhanced system prompt and formatting instructions in `OllamaCoderModelProvider`:
    ```
    CRITICAL FILE PATH REQUIREMENT:
    - You MUST use ONLY the exact relative repository file paths listed in the Located Files above.
    - DO NOT invent, abbreviate, or prepend dummy placeholder directories (e.g., NEVER write "path/to/foo.py" or ".../foo.py").
    - If modifying a file, "path" must exactly equal one of the located files.
    ```

### Component 3: `scripts/v2_2_recovery_manager.py` (Anti-Repetition & Failure Disambiguation)
- **Motivation (Failure Mode E - Blind Repetition Cycles):**
  - In `RETRY_ONLY`, 100% of tasks in Attempts 2 and 3 repeated failed patches byte-for-byte due to deterministic sampling without negative constraints.
- **Implementation:**
  - `ProposalRecord` & `ProposalHistory`: maintains a whitespace-normalized fingerprint of all modification proposals across attempts.
  - `is_repeated(path, operation, anchor, code)`: identifies when a proposal duplicates an earlier attempt.
  - `format_negative_constraints()`: constructs explicit negative directives (`CRITICAL DIRECTIVE: DO NOT REPEAT PREVIOUS FAILED PROPOSALS...`) passed to Coder and Supervisor to force exploration of novel repair hypotheses.
- **Motivation (Failure Mode - Objective Diagnostic Misclassification):**
  - Internal `FailureDetectorAgent` previously mapped AST syntax errors and missing target files to `ANCHOR_NOT_FOUND`, misguiding Supervisor recovery prompts.
- **Implementation:**
  - `FailureDisambiguator.classify()`: accurately categorizes raw execution outcomes into distinct types:
    - `TARGET_FILE_NOT_FOUND`
    - `SYNTAX_ERROR_INDENTATION`
    - `ANCHOR_NOT_FOUND`
    - `ANCHOR_AMBIGUOUS`
    - `REPEATED_PATCH_CYCLE`
    - `P2P_REGRESSION`
    - `F2P_FAILURE`
    - `RESOLVED`

---

## 3. Component Files Modified / Added

| File Path | Status | Purpose |
| :--- | :---: | :--- |
| `scripts/demo_patch_builder.py` | MODIFIED | Indentation normalization, safe path remapping, anchor indent fix. |
| `scripts/ollama_coder_adapter.py` | MODIFIED | Prompt-level path constraints preventing placeholder hallucinations. |
| `scripts/v2_2_recovery_manager.py` | NEW | Anti-repetition tracking and failure disambiguation. |
| `tests/test_v2_2_improvements.py` | NEW | 6 unit tests validating all v2.2 improvements. |
| `scripts/run_v2_2_dev_validation.py` | NEW | Isolated real-repository validation runner on Pylint 4970 & 6903. |
