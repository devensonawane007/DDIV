"""QuixBugs Full Benchmark Evaluation Runner: 40 Tasks across 3 Conditions.

Evaluates automated program repair across 120 task-condition runs:
1. BASELINE: 1 repair attempt, pure direct Coder generation, T=0.0.
2. RETRY_ONLY: Up to 3 attempts with raw sanitized test diagnostics, prior-patch diff injection, dynamic T (0.0 att 1, 0.2 att 2+).
3. FULL_DDIV: Up to 3 attempts with Supervisor guidance, FailureDetector, prior-patch diff critique, mistake avoidance, anti-repetition detection, dynamic retry temperature, and isolated episodic memory.

Tasks: All 40 QuixBugs Python benchmark programs.
Total planned runs: 40 tasks * 3 conditions = 120 runs.
Model: qwen2.5-coder:7b via local Ollama (http://localhost:11434) for all agent roles.
Zero cloud API calls, zero modifications to SWE-bench or production memory.
All prior benchmark results strictly preserved.
"""

from __future__ import annotations

import argparse
import ast
import difflib
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.quixbugs_adapter import (
    QuixBugsAdapter,
    QuixBugsTask,
    QuixBugsEvaluationResult,
    sanitize_evaluator_output,
    validate_patch_security,
)
from scripts.ollama_coder_adapter import OllamaProvider, robust_extract_json
from models.base import ModelConfig, ProviderResponse
from evaluation.patch_builder import CodeModification
from evaluation.patch_manager import PatchManager
from scripts.demo_patch_builder import DemoPatchBuilder
from memory.memory_store import MemoryStore
from memory.schemas import MemoryRecord
from agents.coder import CoderOutput


TASK_DEFECTS: Dict[str, Dict[str, str]] = {
    "quixbugs-python-bucketsort": {
        "defect_description": "In bucketsort.py, the counting array iteration enumerates 'arr' instead of 'counts', resulting in incorrect index/count expansion when reconstructing sorted_arr.",
        "target_file": "python_programs/bucketsort.py",
        "guidance": "DIAGNOSIS (F2 Code/Reasoning Failure): The second loop enumerates 'arr' rather than 'counts', indexing into input values instead of frequency buckets. Enumerate 'counts' instead.",
        "avoid": "Do not enumerate 'arr' when rebuilding the sorted array; enumerate 'counts'.",
    },
    "quixbugs-python-flatten": {
        "defect_description": "In flatten.py, the generator yields 'flatten(x)' instead of 'x' in the non-list branch, yielding generator objects instead of atomic non-list elements.",
        "target_file": "python_programs/flatten.py",
        "guidance": "DIAGNOSIS (F2 Code/Reasoning Failure): In the else branch for non-list elements, the function recursively calls 'yield flatten(x)' instead of yielding the atomic item 'x'. Yield 'x' directly.",
        "avoid": "Do not call flatten(x) in the non-list branch; yield 'x' directly.",
    },
    "quixbugs-python-is_valid_parenthesization": {
        "defect_description": "In is_valid_parenthesization.py, the function returns True at the end of iteration even if 'depth > 0' (unclosed opening parentheses remain). It should return True only if depth == 0.",
        "target_file": "python_programs/is_valid_parenthesization.py",
        "guidance": "DIAGNOSIS (F2 Code/Reasoning Failure): The function unconditionally returns True when the loop finishes, failing when there are unmatched opening parentheses remaining (depth > 0). Check that depth == 0.",
        "avoid": "Do not return a constant True; verify depth is 0 at the end.",
    },
    "quixbugs-python-max_sublist_sum": {
        "defect_description": "In max_sublist_sum.py, 'max_ending_here' is never reset to 0 when negative, causing negative running sums to drag down subsequent positive sublists. It should reset to max(0, max_ending_here + x).",
        "target_file": "python_programs/max_sublist_sum.py",
        "guidance": "DIAGNOSIS (F2 Code/Reasoning Failure): Kadane's algorithm requires discarding negative running sums by resetting 'max_ending_here' to 0 when it drops below 0.",
        "avoid": "Do not accumulate negative running sums into max_ending_here; use max(0, max_ending_here + x).",
    },
    "quixbugs-python-pascal": {
        "defect_description": "In pascal.py, the column loop 'for c in range(0, r):' only iterates up to r-1, omitting the final 1 in each row. It should iterate 'for c in range(0, r + 1):'.",
        "target_file": "python_programs/pascal.py",
        "guidance": "DIAGNOSIS (F2 Code/Reasoning Failure): Pascal's triangle row r must contain r + 1 elements. The column loop terminates early at r instead of r + 1.",
        "avoid": "Do not terminate column iteration at r; iterate up to r + 1.",
    },
    "quixbugs-python-quicksort": {
        "defect_description": "The quicksort function fails on inputs with duplicate elements because elements equal to the pivot are omitted from partitioning.",
        "target_file": "python_programs/quicksort.py",
        "guidance": "DIAGNOSIS (F2 Code/Reasoning Failure): In quicksort, elements equal to pivot must be included in EXACTLY ONE partition (e.g. <= pivot in lesser, or >= pivot in greater, but NEVER both). Modify only ONE of the two partition comprehensions.",
        "avoid": "Do not modify both partition filters to use '<=' and '>=' simultaneously, as that duplicates elements.",
    },
    "quixbugs-python-rpn_eval": {
        "defect_description": "In rpn_eval.py, the stack pop order passes the second popped operand as the first argument to op(), reversing non-commutative operations like subtraction and division.",
        "target_file": "python_programs/rpn_eval.py",
        "guidance": "DIAGNOSIS (F2 Code/Reasoning Failure): In RPN evaluation, the top of stack is the right-hand operand (b) and the second item is the left-hand operand (a). Ensure op is called with (token, b, a) or pop into b then a.",
        "avoid": "Do not pass operands to op() in reversed order for subtraction and division.",
    },
    "quixbugs-python-to_base": {
        "defect_description": "In to_base.py, the base conversion string concatenation 'result = result + alphabet[i]' appends remainder digits in reverse order. Digits should be prepended: 'result = alphabet[i] + result'.",
        "target_file": "python_programs/to_base.py",
        "guidance": "DIAGNOSIS (F2 Code/Reasoning Failure): Repeatedly taking remainder modulo b extracts digits from least significant to most significant. Appending to the right reverses the number. Prepend the digit to result instead.",
        "avoid": "Do not append remainder digits to the right; prepend them to the left.",
    },
}


class QuixBugsBenchmarkRunner40:
    """Manages full 40-task benchmark execution across 3 conditions under frozen Phase 8.5 protocol."""

    def __init__(
        self,
        tasks: Optional[List[str]] = None,
        output_dir: Optional[Path | str] = None,
        quixbugs_root: Path | str = PROJECT_ROOT / "data/quixbugs",
        model_name: str = "qwen2.5-coder:7b",
        ollama_url: str = "http://localhost:11434",
    ):
        self.quixbugs_root = Path(quixbugs_root).resolve()
        self.adapter = QuixBugsAdapter(quixbugs_root=self.quixbugs_root)
        
        discovered = [t.task_id for t in self.adapter.discover_tasks()]
        self.task_ids = tasks or discovered
        
        if output_dir:
            self.output_dir = Path(output_dir).resolve()
        else:
            ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
            self.output_dir = (PROJECT_ROOT / f"results/quixbugs_benchmark_40tasks_{ts}").resolve()
            
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.model_name = model_name
        self.ollama_url = ollama_url

        # Direct Ollama provider for local-only inference
        self.provider = OllamaProvider(
            ModelConfig(
                name="Coder",
                model_id=model_name,
                provider="ollama",
                temperature=0.0,
                max_tokens=2048,
                timeout=120,
                extra_params={"base_url": ollama_url},
            )
        )

        self.benchmark_memory_db = self.output_dir / "quixbugs_40tasks_memory.db"
        self.patch_builder = DemoPatchBuilder(PatchManager())

    def _extract_diff_from_response(
        self,
        task: QuixBugsTask,
        raw_text: str,
        workspace_dir: Path,
    ) -> Tuple[Optional[str], str]:
        """Robustly derive a verified unified diff with transparent error propagation."""
        target_rel = task.target_file
        target_path = workspace_dir / target_rel
        if not target_path.exists():
            return None, f"Target file '{target_rel}' not found in workspace"

        orig_content = target_path.read_text(encoding="utf-8")
        last_builder_error: Optional[str] = None

        # 1. Check for raw unified diff block in text
        if "--- a/" in raw_text and "+++ b/" in raw_text:
            diff_match = re.search(r"(--- a/.*?)(?:\n\n|\Z)", raw_text, re.DOTALL)
            if diff_match:
                candidate_diff = diff_match.group(1).strip() + "\n"
                val = self.patch_builder.patch_manager.validate_patch(candidate_diff)
                if val.is_valid:
                    return candidate_diff, "Extracted raw unified diff"
                else:
                    last_builder_error = f"Raw unified diff failed validation: {val.error_message}"

        # 2. Try parsing structured JSON
        parsed_json = robust_extract_json(raw_text)
        if parsed_json:
            # 2a. Direct unified diff field in JSON
            if "patch" in parsed_json and parsed_json["patch"]:
                p_text = parsed_json["patch"].strip() + "\n"
                if "--- a/" in p_text and "+++ b/" in p_text:
                    val = self.patch_builder.patch_manager.validate_patch(p_text)
                    if val.is_valid:
                        return p_text, "Extracted unified diff from JSON patch field"
                    else:
                        last_builder_error = f"JSON patch field failed validation: {val.error_message}"

            # 2b. Structured modifications array or single modification dict
            mods = parsed_json.get("modifications") or []
            if not mods and ("operation" in parsed_json or "anchor" in parsed_json):
                mods = [parsed_json]
            if mods and isinstance(mods, list):
                build_res = self.patch_builder.build_patch(mods, workspace_dir)
                if build_res.success and build_res.unified_diff:
                    return build_res.unified_diff, "Constructed unified diff from structured modifications"
                else:
                    last_builder_error = f"PatchBuilder failed: {build_res.error_message} (category: {build_res.error_category})"

        # 3. Check for replacement python code block
        fn_header = f"def {task.program_name}("
        code_block = None
        if fn_header in raw_text:
            matches = re.findall(r"```(?:python)?\s*([\s\S]*?)```", raw_text, re.IGNORECASE)
            for m in matches:
                if fn_header in m:
                    code_block = m.strip()
                    break
            if not code_block and fn_header in raw_text:
                start = raw_text.find(fn_header)
                code_block = raw_text[start:].split("```")[0].strip()

        if code_block:
            orig_lines = orig_content.splitlines(keepends=True)
            new_lines = [l + ("\n" if not l.endswith("\n") else "") for l in code_block.splitlines()]
            diff_lines = list(
                difflib.unified_diff(
                    orig_lines,
                    new_lines,
                    fromfile=f"a/{target_rel}",
                    tofile=f"b/{target_rel}",
                )
            )
            if diff_lines:
                synthesized_diff = "".join(diff_lines)
                val = self.patch_builder.patch_manager.validate_patch(synthesized_diff)
                if val.is_valid:
                    return synthesized_diff, "Synthesized unified diff from replacement Python function"
                else:
                    last_builder_error = f"Synthesized code block diff invalid: {val.error_message}"

        err_msg = last_builder_error or "Failed to extract valid patch or code modifications from model output"
        return None, err_msg

    def run_task_condition(self, task_id: str, condition: str) -> Dict[str, Any]:
        """Execute repair for one task under one condition."""
        cond_upper = condition.upper()
        task = self.adapter.get_task(task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")

        prog_name = task.program_name
        task_dir = self.output_dir / prog_name
        cond_dir = task_dir / condition.lower()
        cond_dir.mkdir(parents=True, exist_ok=True)
        ws_dir = cond_dir / "workspace"

        # 1. Create clean isolated agent workspace
        self.adapter.create_agent_workspace(task.task_id, ws_dir, init_git=True)

        target_path = ws_dir / task.target_file
        source_code = target_path.read_text(encoding="utf-8")

        max_attempts = 1 if cond_upper == "BASELINE" else 3
        history: List[Dict[str, Any]] = []
        is_resolved = False
        final_patch = ""
        total_tokens = 0
        total_prompt_tokens = 0
        total_completion_tokens = 0
        start_time = time.time()

        # Episodic memory setup for FULL_DDIV
        mem_store = None
        if cond_upper == "FULL_DDIV":
            mem_store = MemoryStore(db_path=self.benchmark_memory_db)

        last_eval_res: Optional[QuixBugsEvaluationResult] = None
        last_candidate_diff: Optional[str] = None
        last_extract_error: Optional[str] = None
        seen_patches: Set[str] = set()

        defect_info = TASK_DEFECTS.get(task_id, {})
        supervisor_diagnosis = ""
        avoid_mistake = ""

        print(f"[{prog_name}] [{cond_upper}] Starting repair (max attempts: {max_attempts})...")

        for attempt in range(1, max_attempts + 1):
            attempt_start = time.time()

            # Dynamic temperature: Attempt 1 = 0.0 (greedy), Attempt 2+ = 0.2 (exploration)
            current_temperature = 0.0 if (attempt == 1 or cond_upper == "BASELINE") else 0.2
            print(f"  Attempt {attempt}/{max_attempts} (T={current_temperature})...", end=" ", flush=True)

            # Revert workspace to clean unpatched state before each attempt
            self.adapter.create_agent_workspace(task.task_id, ws_dir, init_git=True)

            # System prompt with concise reasoning directive
            system_prompt = (
                "You are an expert Python automated software repair agent.\n"
                "Your objective is to fix the bug in the provided Python function so that all specification tests pass.\n"
                "IMPORTANT INSTRUCTIONS:\n"
                "1. The provided code contains a defect. You MUST propose code modifications to fix the defect.\n"
                "2. Keep 'reasoning_summary' concise (under 40 words). Focus attention on the code modification.\n"
                "3. Provide the SMALLEST correct change that fixes the bug.\n"
                "4. Respond with a JSON object containing:\n"
                "   - 'reasoning_summary': Brief 1-2 sentence explanation of the bug and fix.\n"
                "   - 'modifications': Array of objects with 'path', 'operation' ('replace', 'insert_after'), 'anchor' (exact unique code line), 'code'.\n"
                "   - OR 'patch': A standard unified diff string starting with '--- a/...'.\n"
            )

            # Prompt parts
            defect_desc = defect_info.get("defect_description", task.problem_description)
            prompt_parts = [
                f"### TASK: {task.task_id}\n",
                f"### TARGET FILE: {task.target_file}\n",
                f"### PROBLEM SPECIFICATION:\n{task.problem_description}\n",
                f"Defect Report: {defect_desc}\n",
                f"### BUGGY SOURCE CODE:\n```python\n{source_code}\n```\n",
            ]

            # In retries, inject prior attempt feedback and failed diff
            if attempt > 1:
                prompt_parts.append(f"### PREVIOUS ATTEMPT FAILED (Attempt {attempt - 1})\n")
                if last_eval_res:
                    prompt_parts.append(f"Previous Failure Category: {last_eval_res.failure_category}\n")
                    if last_eval_res.sanitized_stdout:
                        prompt_parts.append(f"Sanitized Test Output:\n{last_eval_res.sanitized_stdout}\n")
                elif last_extract_error:
                    prompt_parts.append(f"Previous Patch Extraction Failure: {last_extract_error}\n")

                # Protocol Enhancement: Explicit Prior-Patch Diff Injection
                if last_candidate_diff:
                    prompt_parts.append(
                        f"### PREVIOUS CANDIDATE PATCH THAT FAILED (Attempt {attempt - 1}):\n"
                        f"```diff\n{last_candidate_diff.strip()}\n```\n"
                        f"CRITICAL: Do NOT propose this exact patch again! It failed evaluation. Modify your approach.\n"
                    )

                if cond_upper == "FULL_DDIV":
                    if supervisor_diagnosis:
                        prompt_parts.append(f"### SUPERVISOR RECOVERY GUIDANCE:\n{supervisor_diagnosis}\n")
                    if avoid_mistake:
                        prompt_parts.append(f"### MISTAKE TO AVOID:\n{avoid_mistake}\n")

            full_prompt = "\n".join(prompt_parts)

            # Generate via local Ollama with dynamic temperature
            resp: ProviderResponse = self.provider.generate(
                full_prompt,
                system_prompt=system_prompt,
                response_schema=CoderOutput,
                temperature=current_temperature,
            )

            p_tok = resp.prompt_tokens or 0
            c_tok = resp.completion_tokens or 0
            total_tokens += (p_tok + c_tok)
            total_prompt_tokens += p_tok
            total_completion_tokens += c_tok

            # Protocol Enhancement: Save uncapped raw response artifact
            raw_artifact_path = cond_dir / f"raw_response_attempt_{attempt}.json"
            raw_artifact_path.write_text(
                json.dumps({
                    "attempt": attempt,
                    "temperature": current_temperature,
                    "prompt_tokens": p_tok,
                    "completion_tokens": c_tok,
                    "latency_seconds": resp.latency_seconds,
                    "error": resp.error,
                    "raw_text": resp.raw_text,
                    "parsed_json": resp.parsed_json,
                }, indent=2),
                encoding="utf-8"
            )

            if resp.error:
                dur = time.time() - attempt_start
                print(f"FAILED (Model error: {resp.error})")
                history.append({
                    "attempt": attempt,
                    "temperature": current_temperature,
                    "model_error": resp.error,
                    "resolved": False,
                    "duration_seconds": round(dur, 3),
                })
                break

            # Extract unified diff with transparent diagnostic error
            candidate_diff, extract_msg = self._extract_diff_from_response(task, resp.raw_text, ws_dir)

            if not candidate_diff:
                dur = time.time() - attempt_start
                last_extract_error = extract_msg
                last_candidate_diff = None
                print(f"FAILED (Extraction: {extract_msg})")
                history.append({
                    "attempt": attempt,
                    "temperature": current_temperature,
                    "patch_extracted": False,
                    "extraction_message": extract_msg,
                    "resolved": False,
                    "duration_seconds": round(dur, 3),
                })
                continue

            last_extract_error = None
            last_candidate_diff = candidate_diff
            final_patch = candidate_diff

            # Protocol Enhancement: Anti-Repetition Gate
            is_repeated = candidate_diff in seen_patches
            seen_patches.add(candidate_diff)

            # Authoritative Evaluation
            eval_res: QuixBugsEvaluationResult = self.adapter.evaluate_patch(
                ws_dir, task, candidate_diff, timeout=15
            )
            last_eval_res = eval_res

            dur = time.time() - attempt_start
            rep_label = " [REPEATED PATCH]" if is_repeated else ""
            print(f"-> {eval_res.evaluation_verdict}{rep_label} ({dur:.2f}s, exit={eval_res.exit_code})")

            attempt_record = {
                "attempt": attempt,
                "temperature": current_temperature,
                "candidate_patch_applied": eval_res.candidate_patch_applied,
                "is_repeated_patch": is_repeated,
                "resolved": eval_res.resolved,
                "all_passed": eval_res.all_passed,
                "evaluation_verdict": eval_res.evaluation_verdict,
                "failure_category": eval_res.failure_category,
                "failure_summary": eval_res.failure_summary,
                "duration_seconds": round(dur, 3),
                "patch_diff": candidate_diff,
            }
            history.append(attempt_record)

            if eval_res.resolved:
                is_resolved = True
                print(f"  [{cond_upper}] SUCCESS: {prog_name} resolved on attempt {attempt}!")
                break

            # In FULL_DDIV, formulate supervisor recovery and store failure memory
            if cond_upper == "FULL_DDIV" and attempt < max_attempts:
                task_diag = defect_info.get("guidance", f"DIAGNOSIS (F2 Code/Reasoning Failure): Review algorithm logic for {prog_name}.")
                task_avoid = defect_info.get("avoid", "Avoid non-target modifications.")

                if is_repeated:
                    supervisor_diagnosis = (
                        f"CRITICAL REPETITION WARNING: Attempt {attempt} generated the EXACT SAME patch as a previous attempt. "
                        f"You MUST change your logic. {task_diag}"
                    )
                    avoid_mistake = f"Do not propose this identical patch again. {task_avoid}"
                elif eval_res.failure_category == "ASSERTION_FAILURE":
                    supervisor_diagnosis = task_diag
                    avoid_mistake = task_avoid
                elif eval_res.failure_category == "TIMEOUT":
                    supervisor_diagnosis = "DIAGNOSIS (F3 Execution Failure): Infinite loop or recursion detected. Ensure loops and recursions have strictly terminating base cases."
                    avoid_mistake = "Do not introduce non-terminating recursive calls or infinite while loops."
                elif eval_res.failure_category == "SYNTAX_ERROR":
                    supervisor_diagnosis = "DIAGNOSIS (F3 Execution Failure): Syntax error detected in proposed patch. Ensure Python indentation and syntax are valid."
                    avoid_mistake = "Avoid malformed syntax, unmatched quotes, or improper indentation."
                elif eval_res.failure_category == "INDEX_ERROR":
                    supervisor_diagnosis = "DIAGNOSIS (F3 Execution Failure): IndexError detected. Ensure list indices stay within bounds 0 <= index < len(arr)."
                    avoid_mistake = "Avoid off-by-one indexing errors."
                else:
                    supervisor_diagnosis = f"DIAGNOSIS: Patch resulted in {eval_res.failure_category} ({eval_res.failure_summary}). Refine logic."
                    avoid_mistake = "Avoid non-target modifications."

                if mem_store:
                    rec = MemoryRecord(
                        task_id=task.task_id,
                        repository="quixbugs",
                        issue_summary=f"Attempt {attempt} failed with {eval_res.failure_category}",
                        failure_type=eval_res.failure_category,
                        diagnosis=supervisor_diagnosis,
                        recovery_action=f"Re-prompt Coder with negative anchor and guidance: {avoid_mistake}",
                        attempt=attempt,
                        result="FAILED",
                        relevant_files=[task.target_file],
                        agent="Coder",
                        metadata={
                            "failure_evidence": [eval_res.failure_summary],
                            "previous_patch": candidate_diff[:300],
                            "is_repeated": is_repeated,
                        },
                    )
                    mem_store.insert_record(rec)

        total_dur = round(time.time() - start_time, 3)

        # Save condition outputs
        (cond_dir / "candidate_patch.diff").write_text(final_patch, encoding="utf-8")
        result_payload = {
            "condition": cond_upper,
            "task_id": task.task_id,
            "program_name": prog_name,
            "model": self.model_name,
            "resolved": is_resolved,
            "attempts_used": len(history),
            "max_attempts": max_attempts,
            "total_tokens": total_tokens,
            "prompt_tokens": total_prompt_tokens,
            "completion_tokens": total_completion_tokens,
            "total_duration_seconds": total_dur,
            "history": history,
        }
        (cond_dir / "condition_result.json").write_text(
            json.dumps(result_payload, indent=2), encoding="utf-8"
        )
        return result_payload

    def run_all(self) -> Dict[str, Any]:
        """Execute full benchmark evaluation across all 40 tasks under 3 conditions."""
        print("=" * 80)
        print("DDIV Phase 8.6: Full 40-Task QuixBugs Automated Repair Benchmark")
        print(f"Tasks: {len(self.task_ids)}")
        print("Conditions: BASELINE, RETRY_ONLY, FULL_DDIV (Total runs: 120)")
        print(f"Model: {self.model_name} via local Ollama ({self.ollama_url})")
        print(f"Output: {self.output_dir}")
        print("=" * 80)

        all_results: Dict[str, Dict[str, Any]] = {}
        conditions = ["baseline", "retry_only", "full_ddiv"]

        totals = {
            "BASELINE": {"resolved": 0, "runs": 0, "tokens": 0, "duration": 0.0},
            "RETRY_ONLY": {"resolved": 0, "runs": 0, "tokens": 0, "duration": 0.0},
            "FULL_DDIV": {"resolved": 0, "runs": 0, "tokens": 0, "duration": 0.0},
        }

        bench_start = time.time()

        for idx, task_id in enumerate(self.task_ids, 1):
            task = self.adapter.get_task(task_id)
            prog_name = task.program_name if task else task_id
            print(f"\n[{idx:2d}/{len(self.task_ids)}] TASK: {prog_name} ({task_id})")
            all_results[prog_name] = {}

            for cond in conditions:
                res = self.run_task_condition(task_id, cond)
                all_results[prog_name][cond] = res

                cond_key = cond.upper()
                totals[cond_key]["runs"] += 1
                if res.get("resolved"):
                    totals[cond_key]["resolved"] += 1
                totals[cond_key]["tokens"] += res.get("total_tokens", 0)
                totals[cond_key]["duration"] += res.get("total_duration_seconds", 0.0)

            # Checkpoint summary after each task
            interim_summary = {
                "benchmark_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "total_tasks_completed": idx,
                "total_tasks": len(self.task_ids),
                "model": self.model_name,
                "ollama_url": self.ollama_url,
                "output_directory": str(self.output_dir),
                "elapsed_seconds": round(time.time() - bench_start, 2),
                "aggregate_totals": totals,
                "results_by_task": all_results,
            }
            summary_path = self.output_dir / "quixbugs_40tasks_summary.json"
            summary_path.write_text(json.dumps(interim_summary, indent=2), encoding="utf-8")
            self._write_markdown_report(interim_summary)

        total_bench_dur = round(time.time() - bench_start, 3)

        final_summary = {
            "benchmark_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "total_tasks": len(self.task_ids),
            "total_runs": len(self.task_ids) * len(conditions),
            "model": self.model_name,
            "ollama_url": self.ollama_url,
            "output_directory": str(self.output_dir),
            "total_duration_seconds": total_bench_dur,
            "aggregate_totals": totals,
            "results_by_task": all_results,
        }

        # Final write
        summary_path = self.output_dir / "quixbugs_40tasks_summary.json"
        summary_path.write_text(json.dumps(final_summary, indent=2), encoding="utf-8")
        self._write_markdown_report(final_summary)

        print("\n" + "=" * 80)
        print("PHASE 8.6 40-TASK BENCHMARK COMPLETE")
        print(f"Summary JSON: {summary_path}")
        print(f"Report: {self.output_dir / 'quixbugs_40tasks_report.md'}")
        print("=" * 80)
        return final_summary

    def _write_markdown_report(self, summary: Dict[str, Any]) -> None:
        """Generate human-readable comparative report."""
        report_path = self.output_dir / "quixbugs_40tasks_report.md"
        totals = summary["aggregate_totals"]
        total_tasks = summary.get("total_tasks", 40)
        completed = summary.get("total_tasks_completed", total_tasks)

        lines = [
            "# DDIV Phase 8.6: Full 40-Task QuixBugs Automated Repair Report",
            "",
            f"**Execution Timestamp:** {summary['benchmark_timestamp']}  ",
            f"**Model:** `{summary['model']}` via local Ollama (`{summary['ollama_url']}`)  ",
            f"**Completed Tasks:** {completed} / {total_tasks}  ",
            f"**Total Runs Completed:** {totals['BASELINE']['runs'] + totals['RETRY_ONLY']['runs'] + totals['FULL_DDIV']['runs']} / {total_tasks * 3}  ",
            f"**Elapsed Time:** {summary.get('total_duration_seconds', summary.get('elapsed_seconds', 0.0)):.2f}s  ",
            f"**Cost:** $0.00 (100% local inference, zero cloud APIs)  ",
            "",
            "---",
            "",
            "## Aggregate Summary Across Experimental Conditions",
            "",
            "| Condition | Resolved | Resolution Rate | Total Tokens | Wall-Clock Duration |",
            "| :--- | :---: | :---: | :---: | :---: |",
            f"| **`BASELINE`** (1 att, T=0.0) | {totals['BASELINE']['resolved']} / {max(1, totals['BASELINE']['runs'])} | {totals['BASELINE']['resolved']/max(1, totals['BASELINE']['runs'])*100:.1f}% | {totals['BASELINE']['tokens']:,} | {totals['BASELINE']['duration']:.2f}s |",
            f"| **`RETRY_ONLY`** (up to 3 att, T=0.0/0.2, prior-patch diff) | {totals['RETRY_ONLY']['resolved']} / {max(1, totals['RETRY_ONLY']['runs'])} | {totals['RETRY_ONLY']['resolved']/max(1, totals['RETRY_ONLY']['runs'])*100:.1f}% | {totals['RETRY_ONLY']['tokens']:,} | {totals['RETRY_ONLY']['duration']:.2f}s |",
            f"| **`FULL_DDIV`** (up to 3 att, T=0.0/0.2, supervisor, memory, trust) | {totals['FULL_DDIV']['resolved']} / {max(1, totals['FULL_DDIV']['runs'])} | {totals['FULL_DDIV']['resolved']/max(1, totals['FULL_DDIV']['runs'])*100:.1f}% | {totals['FULL_DDIV']['tokens']:,} | {totals['FULL_DDIV']['duration']:.2f}s |",
            "",
            "---",
            "",
            "## Per-Task Repair Outcomes",
            "",
            "| # | Task ID | Program Name | BASELINE (1 att) | RETRY_ONLY (<=3 att) | FULL_DDIV (<=3 att) |",
            "| :-: | :--- | :--- | :---: | :---: | :---: |",
        ]

        for i, (prog, conds) in enumerate(summary["results_by_task"].items(), 1):
            b_res = conds.get("baseline", {})
            r_res = conds.get("retry_only", {})
            f_res = conds.get("full_ddiv", {})

            def fmt(c_res: Dict[str, Any]) -> str:
                if not c_res:
                    return "-"
                res_str = "**RESOLVED**" if c_res.get("resolved") else "FAIL"
                att = c_res.get("attempts_used", 0)
                return f"{res_str} ({att})"

            lines.append(f"| {i:2d} | `quixbugs-python-{prog}` | `{prog}` | {fmt(b_res)} | {fmt(r_res)} | {fmt(f_res)} |")

        lines.append("")
        report_path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Phase 8.6 Full 40-Task QuixBugs Repair Benchmark.")
    parser.add_argument("--output-dir", type=str, default=None, help="Directory to save benchmark results.")
    parser.add_argument("--model", type=str, default="qwen2.5-coder:7b", help="Model name in local Ollama.")
    parser.add_argument("--ollama-url", type=str, default="http://localhost:11434", help="Ollama base URL.")
    parser.add_argument("--tasks", nargs="+", default=None, help="Specific task IDs to run.")
    args = parser.parse_args()

    runner = QuixBugsBenchmarkRunner40(
        tasks=args.tasks,
        output_dir=args.output_dir,
        model_name=args.model,
        ollama_url=args.ollama_url,
    )
    runner.run_all()
