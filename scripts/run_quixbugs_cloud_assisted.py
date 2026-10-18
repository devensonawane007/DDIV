#!/usr/bin/env python3
"""
DDIV Phase 8.8.3 Runner: Cloud-Assisted Multi-Agent QuixBugs Automated Program Repair.

Evaluates the canonical challenge set of 27 QuixBugs tasks unresolved by local FULL_DDIV.
Implements Option A (Hybrid Architecture):
- Locator: Gemini gemini-3.1-flash-lite (Cloud)
- Supervisor: Groq qwen/qwen3.8-27b (Cloud)
- Tester: Groq qwen/qwen3.8-27b (Cloud)
- Coder: Local Ollama qwen2.5-coder:7b (Local GPU, $0.00 cost)

Phase 8.8.3 Enhancements:
- Deterministic --batch {1,2,3} and --batch-manifest support.
- Strict checkpoint validation: skips only complete, validated results matching config.
- Granular token accounting: tracks prompt/completion tokens by provider, role, task, and attempt.
- Cumulative token persistence across process restarts in cumulative_token_usage.json.
- Configurable daily token ceilings (--max-daily-groq-tokens, --max-daily-gemini-tokens).
- Provider response header rate-limit handling (TPM protection and dynamic reset backoff).
- Disabled automatic model/provider fallback (strictly enforces Option A).
- Safe halt on HTTP 429, quota exhaustion, or budget limits without corrupting memory or data.
- Shared episodic memory preserved across batches in quixbugs_cloud_assisted_memory.db.
- Zero modification to production database data/ddiv_memory.db or historical benchmarks.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shutil
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config import AgentModelConfig, DDIVConfig, ExecutionMode
from evaluation.quixbugs_adapter import (
    QuixBugsAdapter,
    QuixBugsEvaluationResult,
    QuixBugsTask,
    sanitize_evaluator_output,
    validate_patch_security,
)
from models.base import ModelConfig, ModelProvider, ProviderResponse
from models.providers import GeminiProvider, GroqProvider
from scripts.ollama_coder_adapter import OllamaProvider, robust_extract_json
from scripts.demo_patch_builder import DemoPatchBuilder
from memory.memory_store import MemoryStore
from memory.schemas import MemoryRecord
from agents.coder import CoderOutput


class RateLimitQuotaException(Exception):
    """Raised when an API rate limit or daily token quota ceiling is reached."""
    pass


def parse_header_duration(duration_str: str) -> float:
    """Parse duration strings like '250ms', '1.5s', '6s', '2m30s' into float seconds."""
    if not duration_str:
        return 0.0
    s = str(duration_str).strip().lower()
    try:
        # Simple float/int seconds
        return float(s)
    except ValueError:
        pass

    # Milliseconds: '250ms'
    if s.endswith("ms"):
        try:
            return float(s[:-2]) / 1000.0
        except ValueError:
            return 0.0

    # Seconds: '5s'
    if s.endswith("s") and not s.endswith("ms"):
        try:
            return float(s[:-1])
        except ValueError:
            pass

    # Minutes/seconds: '1m30s'
    m_match = re.match(r"(?:(\d+)m)?(?:(\d+(?:\.\d+)?)s)?", s)
    if m_match:
        minutes = float(m_match.group(1) or 0)
        seconds = float(m_match.group(2) or 0)
        return (minutes * 60.0) + seconds

    return 0.0


def handle_rate_limit_headers(
    headers: Optional[Dict[str, Any]],
    default_delay: float = 0.0,
    min_token_headroom: int = 3000,
) -> float:
    """
    Examines rate-limit response headers and applies throttling if token headroom is low.
    Returns the number of seconds paused.
    """
    if not headers:
        if default_delay > 0:
            time.sleep(default_delay)
            return default_delay
        return 0.0

    headers_lower = {k.lower(): v for k, v in headers.items()}
    sleep_needed = default_delay

    # 1. Check retry-after header
    retry_after_str = headers_lower.get("retry-after")
    if retry_after_str:
        try:
            retry_sec = float(retry_after_str)
            sleep_needed = max(sleep_needed, retry_sec + 0.5)
        except ValueError:
            pass

    # 2. Check remaining tokens
    rem_tokens_str = headers_lower.get("x-ratelimit-remaining-tokens")
    if rem_tokens_str:
        try:
            rem_tokens = int(rem_tokens_str)
            if rem_tokens < min_token_headroom:
                reset_duration_str = headers_lower.get("x-ratelimit-reset-tokens", "2s")
                reset_sec = parse_header_duration(reset_duration_str)
                sleep_needed = max(sleep_needed, reset_sec + 0.5)
        except ValueError:
            pass

    # 3. Check remaining requests
    rem_req_str = headers_lower.get("x-ratelimit-remaining-requests")
    if rem_req_str:
        try:
            rem_req = int(rem_req_str)
            if rem_req <= 1:
                reset_req_str = headers_lower.get("x-ratelimit-reset-requests", "2s")
                reset_sec = parse_header_duration(reset_req_str)
                sleep_needed = max(sleep_needed, reset_sec + 0.5)
        except ValueError:
            pass

    if sleep_needed > 0:
        time.sleep(sleep_needed)
    return sleep_needed


def validate_checkpoint_result(
    result_path: Path,
    expected_task_id: str,
    expected_prog_name: str,
    max_attempts: int,
) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    """
    Authoritative validation of existing condition_result.json.
    Returns (is_valid, parsed_result, reason).
    A result is valid ONLY IF:
    - Parsable JSON
    - condition == 'CLOUD_ASSISTED_DDIV'
    - Matches expected task_id and program_name
    - history is non-empty list of attempts
    - Either resolved is True OR attempts_used == max_attempts (authoritative exhaustion).
      Interrupted or partial failures (attempts_used < max_attempts with resolved=False) are rejected.
    """
    if not result_path.exists():
        return False, None, "File does not exist"

    try:
        content = result_path.read_text(encoding="utf-8")
        if not content.strip():
            return False, None, "File is empty"
        data = json.loads(content)
    except Exception as e:
        return False, None, f"JSON parse error: {e}"

    if data.get("condition") != "CLOUD_ASSISTED_DDIV":
        return False, None, f"Mismatched condition: {data.get('condition')}"

    if data.get("task_id") != expected_task_id:
        return False, None, f"Mismatched task_id: expected {expected_task_id}, got {data.get('task_id')}"

    if data.get("program_name") != expected_prog_name:
        return False, None, f"Mismatched program_name: expected {expected_prog_name}, got {data.get('program_name')}"

    history = data.get("history")
    if not isinstance(history, list) or len(history) == 0:
        return False, None, "History list is missing or empty"

    is_resolved = bool(data.get("resolved", False))
    attempts_used = data.get("attempts_used", len(history))

    if is_resolved:
        # Check that candidate_patch.diff exists
        diff_file = result_path.parent / "candidate_patch.diff"
        if not diff_file.exists():
            return False, None, "Resolved result missing candidate_patch.diff"
        return True, data, "Valid resolved task"

    # If unresolved, it must have authoritatively completed all max_attempts
    if attempts_used < max_attempts:
        return (
            False,
            None,
            f"Partial/interrupted failure: completed {attempts_used}/{max_attempts} attempts",
        )

    return True, data, f"Valid authoritative failure ({attempts_used}/{max_attempts} attempts)"


class CumulativeTokenTracker:
    """Tracks token usage across providers, roles, tasks, attempts, and process restarts."""

    def __init__(self, persistence_path: Optional[Path] = None):
        self.persistence_path = Path(persistence_path) if persistence_path else None
        self.transactions: List[Dict[str, Any]] = []

        # Session totals
        self.session_by_provider: Dict[str, Dict[str, int]] = {
            "gemini": {"prompt": 0, "completion": 0, "total": 0},
            "groq": {"prompt": 0, "completion": 0, "total": 0},
            "ollama": {"prompt": 0, "completion": 0, "total": 0},
        }
        self.session_by_role: Dict[str, Dict[str, int]] = {
            "Locator": {"prompt": 0, "completion": 0, "total": 0},
            "Supervisor": {"prompt": 0, "completion": 0, "total": 0},
            "Tester": {"prompt": 0, "completion": 0, "total": 0},
            "Coder": {"prompt": 0, "completion": 0, "total": 0},
        }

        # Daily usage partitioned by UTC date: "YYYY-MM-DD" -> provider -> {"prompt": int, "completion": int, "total": int}
        self.usage_by_date: Dict[str, Dict[str, Dict[str, int]]] = {}

        # Prior cumulative totals loaded from disk
        self.cumulative_by_provider: Dict[str, Dict[str, int]] = {
            "gemini": {"prompt": 0, "completion": 0, "total": 0},
            "groq": {"prompt": 0, "completion": 0, "total": 0},
            "ollama": {"prompt": 0, "completion": 0, "total": 0},
        }
        self.cumulative_by_role: Dict[str, Dict[str, int]] = {
            "Locator": {"prompt": 0, "completion": 0, "total": 0},
            "Supervisor": {"prompt": 0, "completion": 0, "total": 0},
            "Tester": {"prompt": 0, "completion": 0, "total": 0},
            "Coder": {"prompt": 0, "completion": 0, "total": 0},
        }
        self.session_count = 1

        self.load_prior_cumulative()

    def load_prior_cumulative(self):
        """Loads prior cumulative tokens and date-partitioned usage from disk if available."""
        if not self.persistence_path or not self.persistence_path.exists():
            return

        try:
            data = json.loads(self.persistence_path.read_text(encoding="utf-8"))
            self.session_count = data.get("session_count", 0) + 1
            for p, counts in data.get("totals_by_provider", {}).items():
                if p not in self.cumulative_by_provider:
                    self.cumulative_by_provider[p] = {"prompt": 0, "completion": 0, "total": 0}
                self.cumulative_by_provider[p]["prompt"] = counts.get("prompt", 0)
                self.cumulative_by_provider[p]["completion"] = counts.get("completion", 0)
                self.cumulative_by_provider[p]["total"] = counts.get("total", 0)

            for r, counts in data.get("totals_by_role", {}).items():
                if r not in self.cumulative_by_role:
                    self.cumulative_by_role[r] = {"prompt": 0, "completion": 0, "total": 0}
                self.cumulative_by_role[r]["prompt"] = counts.get("prompt", 0)
                self.cumulative_by_role[r]["completion"] = counts.get("completion", 0)
                self.cumulative_by_role[r]["total"] = counts.get("total", 0)

            for d_str, prov_map in data.get("usage_by_date", {}).items():
                if d_str not in self.usage_by_date:
                    self.usage_by_date[d_str] = {}
                for p, counts in prov_map.items():
                    self.usage_by_date[d_str][p] = {
                        "prompt": counts.get("prompt", 0),
                        "completion": counts.get("completion", 0),
                        "total": counts.get("total", 0),
                    }
        except Exception as e:
            print(f"Warning: Could not parse prior token persistence file: {e}")

    def record(
        self,
        task_id: str,
        program_name: str,
        attempt: int,
        role: str,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> Dict[str, Any]:
        """Record a single token transaction and update session, daily, and cumulative totals."""
        p_tok = max(0, int(prompt_tokens or 0))
        c_tok = max(0, int(completion_tokens or 0))
        tot_tok = p_tok + c_tok
        p_name = provider.lower()
        date_str = time.strftime("%Y-%m-%d", time.gmtime())

        tx = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "date_utc": date_str,
            "task_id": task_id,
            "program_name": program_name,
            "attempt": attempt,
            "role": role,
            "provider": p_name,
            "model": model,
            "prompt_tokens": p_tok,
            "completion_tokens": c_tok,
            "total_tokens": tot_tok,
        }
        self.transactions.append(tx)

        # Update session provider totals
        if p_name not in self.session_by_provider:
            self.session_by_provider[p_name] = {"prompt": 0, "completion": 0, "total": 0}
        self.session_by_provider[p_name]["prompt"] += p_tok
        self.session_by_provider[p_name]["completion"] += c_tok
        self.session_by_provider[p_name]["total"] += tot_tok

        # Update session role totals
        if role not in self.session_by_role:
            self.session_by_role[role] = {"prompt": 0, "completion": 0, "total": 0}
        self.session_by_role[role]["prompt"] += p_tok
        self.session_by_role[role]["completion"] += c_tok
        self.session_by_role[role]["total"] += tot_tok

        # Update daily date-partitioned usage (UTC calendar date)
        if date_str not in self.usage_by_date:
            self.usage_by_date[date_str] = {}
        if p_name not in self.usage_by_date[date_str]:
            self.usage_by_date[date_str][p_name] = {"prompt": 0, "completion": 0, "total": 0}
        self.usage_by_date[date_str][p_name]["prompt"] += p_tok
        self.usage_by_date[date_str][p_name]["completion"] += c_tok
        self.usage_by_date[date_str][p_name]["total"] += tot_tok

        # Update cumulative provider totals
        if p_name not in self.cumulative_by_provider:
            self.cumulative_by_provider[p_name] = {"prompt": 0, "completion": 0, "total": 0}
        self.cumulative_by_provider[p_name]["prompt"] += p_tok
        self.cumulative_by_provider[p_name]["completion"] += c_tok
        self.cumulative_by_provider[p_name]["total"] += tot_tok

        # Update cumulative role totals
        if role not in self.cumulative_by_role:
            self.cumulative_by_role[role] = {"prompt": 0, "completion": 0, "total": 0}
        self.cumulative_by_role[role]["prompt"] += p_tok
        self.cumulative_by_role[role]["completion"] += c_tok
        self.cumulative_by_role[role]["total"] += tot_tok

        return tx

    def get_session_provider_total(self, provider: str) -> int:
        """Returns total session tokens for a given provider."""
        return self.session_by_provider.get(provider.lower(), {}).get("total", 0)

    def get_daily_provider_total(self, provider: str, date_str: Optional[str] = None) -> int:
        """Returns total tokens consumed for a given provider on a specific UTC date."""
        d = date_str or time.strftime("%Y-%m-%d", time.gmtime())
        return self.usage_by_date.get(d, {}).get(provider.lower(), {}).get("total", 0)

    def get_task_breakdown(self, task_id: str) -> Dict[str, Any]:
        """Calculates breakdown for a specific task."""
        txs = [t for t in self.transactions if t["task_id"] == task_id]
        by_role: Dict[str, Dict[str, int]] = {}
        by_provider: Dict[str, Dict[str, int]] = {}

        for tx in txs:
            r = tx["role"]
            p = tx["provider"]
            if r not in by_role:
                by_role[r] = {"prompt": 0, "completion": 0, "total": 0}
            by_role[r]["prompt"] += tx["prompt_tokens"]
            by_role[r]["completion"] += tx["completion_tokens"]
            by_role[r]["total"] += tx["total_tokens"]

            if p not in by_provider:
                by_provider[p] = {"prompt": 0, "completion": 0, "total": 0}
            by_provider[p]["prompt"] += tx["prompt_tokens"]
            by_provider[p]["completion"] += tx["completion_tokens"]
            by_provider[p]["total"] += tx["total_tokens"]

        total_tokens = sum(tx["total_tokens"] for tx in txs)
        prompt_tokens = sum(tx["prompt_tokens"] for tx in txs)
        completion_tokens = sum(tx["completion_tokens"] for tx in txs)

        return {
            "total_tokens": total_tokens,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "by_role": by_role,
            "by_provider": by_provider,
            "transactions": txs,
        }

    def persist(self):
        """Persists cumulative usage and daily date buckets to JSON file."""
        if not self.persistence_path:
            return

        grand_total = sum(v["total"] for v in self.cumulative_by_provider.values())
        payload = {
            "last_updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "session_count": self.session_count,
            "usage_by_date": self.usage_by_date,
            "totals_by_provider": self.cumulative_by_provider,
            "totals_by_role": self.cumulative_by_role,
            "grand_total_tokens": grand_total,
            "current_session_provider_tokens": self.session_by_provider,
            "current_session_role_tokens": self.session_by_role,
        }
        self.persistence_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class QuixBugsCloudAssistedRunner:
    """Manages cloud-assisted multi-agent repair on the 27 unresolved QuixBugs tasks."""

    def __init__(
        self,
        task_manifest_path: Path | str,
        output_dir: Path | str,
        quixbugs_root: Path | str = PROJECT_ROOT / "data/quixbugs",
        max_attempts: int = 3,
        coder_provider: str = "ollama",
        batch: Optional[int] = None,
        batch_manifest_path: Optional[Path | str] = None,
        max_daily_groq_tokens: int = 100000,
        max_daily_gemini_tokens: int = 30000,
        pacing_delay: float = 10.0,
        # Allow injecting mock providers for testing
        locator_provider: Optional[ModelProvider] = None,
        supervisor_provider: Optional[ModelProvider] = None,
        tester_provider: Optional[ModelProvider] = None,
        coder_provider_instance: Optional[ModelProvider] = None,
    ):
        self.quixbugs_root = Path(quixbugs_root).resolve()
        self.output_dir = Path(output_dir).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.max_attempts = max_attempts
        self.coder_provider_name = coder_provider.lower()
        self.batch = batch
        self.max_daily_groq_tokens = max_daily_groq_tokens
        self.max_daily_gemini_tokens = max_daily_gemini_tokens
        self.pacing_delay = pacing_delay

        # Token Tracker
        self.token_tracker = CumulativeTokenTracker(
            persistence_path=self.output_dir / "cumulative_token_usage.json"
        )

        # Load environment variables
        self.config = DDIVConfig.load_from_env()

        # Initialize QuixBugs Adapter
        self.adapter = QuixBugsAdapter(quixbugs_root=self.quixbugs_root)

        # Load tasks from manifest
        manifest_p = Path(task_manifest_path).resolve()
        if not manifest_p.exists():
            raise FileNotFoundError(f"Task manifest not found at: {manifest_p}")
        manifest_data = json.loads(manifest_p.read_text(encoding="utf-8"))
        all_tasks = manifest_data.get("tasks", [])

        # Filter by batch if specified
        if batch is not None:
            if batch not in (1, 2, 3):
                raise ValueError(f"Invalid batch number {batch}. Expected 1, 2, or 3.")

            batch_tasks = []
            if batch_manifest_path and Path(batch_manifest_path).exists():
                b_data = json.loads(Path(batch_manifest_path).read_text(encoding="utf-8"))
                for b_entry in b_data.get("batches", []):
                    if b_entry.get("batch_id") == f"batch_{batch}":
                        target_ids = {t["canonical_task_id"] for t in b_entry.get("tasks", [])}
                        batch_tasks = [t for t in all_tasks if t["canonical_task_id"] in target_ids]
                        break
            
            # Fallback deterministic slice if batch manifest not found
            if not batch_tasks:
                start_idx = (batch - 1) * 9
                end_idx = start_idx + 9
                batch_tasks = all_tasks[start_idx:end_idx]

            self.manifest_tasks = batch_tasks
        else:
            self.manifest_tasks = all_tasks

        self.task_ids = [t["canonical_task_id"] for t in self.manifest_tasks]

        # Isolated memory store in output directory
        self.memory_db_path = self.output_dir / "quixbugs_cloud_assisted_memory.db"
        self.mem_store = MemoryStore(db_path=self.memory_db_path)

        # ---------------------------------------------------------------------
        # Agent Provider Initialization (Option A Routing)
        # Strictly disables automatic fallback to preserve research reproducibility.
        # ---------------------------------------------------------------------
        if locator_provider is not None:
            self.locator_provider = locator_provider
        else:
            loc_cfg = ModelConfig(
                name="Locator",
                model_id=os.getenv("LOCATOR_MODEL", "gemini-3.1-flash-lite"),
                provider="gemini",
                api_key=os.getenv("GEMINI_API_KEY"),
                base_url=os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"),
                temperature=0.0,
                max_tokens=2048,
                timeout=120,
                disable_fallback=True,
            )
            self.locator_provider = GeminiProvider(loc_cfg)

        if supervisor_provider is not None:
            self.supervisor_provider = supervisor_provider
        else:
            sup_cfg = ModelConfig(
                name="Supervisor",
                model_id=os.getenv("SUPERVISOR_MODEL", "qwen/qwen3.8-27b"),
                provider="groq",
                api_key=os.getenv("GROQ_API_KEY"),
                base_url=os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
                temperature=0.0,
                max_tokens=400,
                timeout=120,
                max_retries=3,
                disable_fallback=True,
            )
            self.supervisor_provider = GroqProvider(sup_cfg)

        if tester_provider is not None:
            self.tester_provider = tester_provider
        else:
            test_cfg = ModelConfig(
                name="Tester",
                model_id=os.getenv("TESTER_MODEL", "qwen/qwen3.8-27b"),
                provider="groq",
                api_key=os.getenv("GROQ_API_KEY"),
                base_url=os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
                temperature=0.0,
                max_tokens=500,
                timeout=120,
                max_retries=3,
                disable_fallback=True,
            )
            self.tester_provider = GroqProvider(test_cfg)

        if coder_provider_instance is not None:
            self.coder_provider = coder_provider_instance
        elif self.coder_provider_name == "ollama":
            coder_cfg = ModelConfig(
                name="Coder",
                model_id=os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b"),
                provider="ollama",
                temperature=0.0,
                max_tokens=2048,
                timeout=180,
                disable_fallback=True,
                extra_params={"base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")},
            )
            self.coder_provider = OllamaProvider(coder_cfg)
        else:
            coder_cfg = ModelConfig(
                name="Coder",
                model_id=os.getenv("CODER_MODEL", "openai/gpt-oss-120b"),
                provider="groq",
                api_key=os.getenv("GROQ_API_KEY"),
                base_url=os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
                temperature=0.0,
                max_tokens=3072,
                timeout=180,
                disable_fallback=True,
            )
            self.coder_provider = GroqProvider(coder_cfg)

    def _check_budget_limits(self, role: str, provider: str, est_tokens: int = 2500):
        """Raises RateLimitQuotaException if daily token ceilings would be exceeded on current UTC date."""
        p_name = provider.lower()
        today_str = time.strftime("%Y-%m-%d", time.gmtime())
        current_daily = self.token_tracker.get_daily_provider_total(p_name, today_str)

        if p_name == "groq":
            if current_daily + est_tokens > self.max_daily_groq_tokens:
                raise RateLimitQuotaException(
                    f"Daily Groq token ceiling exceeded for {today_str}: current usage {current_daily} + est {est_tokens} "
                    f"> limit {self.max_daily_groq_tokens}. Safe halt to prevent quota violation."
                )
        elif p_name == "gemini":
            if current_daily + est_tokens > self.max_daily_gemini_tokens:
                raise RateLimitQuotaException(
                    f"Daily Gemini token ceiling exceeded for {today_str}: current usage {current_daily} + est {est_tokens} "
                    f"> limit {self.max_daily_gemini_tokens}. Safe halt to prevent quota violation."
                )

    def _extract_diff_from_response(self, task: QuixBugsTask, raw_text: str, ws_dir: Path) -> Tuple[str, str]:
        """Extract valid unified diff using DemoPatchBuilder with syntax verification."""
        parsed = robust_extract_json(raw_text)
        if not parsed:
            return "", "Failed to extract valid JSON from model response"
        mods_data = parsed.get("modifications", [])
        if not mods_data:
            return "", "JSON response contained no modifications"

        mods = []
        for m in mods_data:
            mods.append({
                "path": m.get("path", task.target_file),
                "operation": m.get("operation", "replace"),
                "anchor": m.get("anchor", ""),
                "code": m.get("code", ""),
            })

        diff_res = DemoPatchBuilder().build_patch(mods, ws_dir)
        if diff_res.success:
            return diff_res.unified_diff, "Success"
        return "", diff_res.error_message or "PatchBuilder failed"

    def run_task(self, task: QuixBugsTask) -> Dict[str, Any]:
        """Execute cloud-assisted multi-agent repair on a single task."""
        prog_name = task.program_name
        task_dir = self.output_dir / prog_name
        task_dir.mkdir(parents=True, exist_ok=True)
        ws_dir = task_dir / "workspace"

        # Initialize clean isolated workspace
        self.adapter.create_agent_workspace(task.task_id, ws_dir)

        history: List[Dict[str, Any]] = []
        is_resolved = False
        seen_patches: Set[str] = set()
        final_patch = ""

        start_time = time.time()
        last_candidate_diff = ""
        last_eval_res: Optional[QuixBugsEvaluationResult] = None
        last_extract_error = ""

        # Target file source code
        prog_file = ws_dir / task.target_file
        source_code = prog_file.read_text(encoding="utf-8") if prog_file.exists() else ""

        # ---------------------------------------------------------------------
        # Step 1: Fault Localization (Locator: Gemini)
        # ---------------------------------------------------------------------
        self._check_budget_limits("Locator", "gemini", est_tokens=2000)
        loc_prompt = (
            f"You are an expert Fault Localization agent. Analyze the following Python program from QuixBugs:\n\n"
            f"Program File: {task.target_file}\n"
            f"```python\n{source_code}\n```\n\n"
            f"Identify the exact buggy line(s), explain the algorithmic flaw, and specify which lines must be modified."
        )
        loc_resp: ProviderResponse = self.locator_provider.generate(loc_prompt)

        # Check for rate-limiting or quota exhaustion
        if loc_resp.error_category == "RATE_LIMITED":
            raise RateLimitQuotaException(f"Locator (Gemini) was rate-limited: {loc_resp.error}")

        # Throttling & Header Rate-Limiting
        handle_rate_limit_headers(loc_resp.rate_limit_headers, default_delay=self.pacing_delay)

        locator_analysis = loc_resp.raw_text
        self.token_tracker.record(
            task_id=task.task_id,
            program_name=prog_name,
            attempt=0,
            role="Locator",
            provider="gemini",
            model=loc_resp.model_id,
            prompt_tokens=loc_resp.prompt_tokens,
            completion_tokens=loc_resp.completion_tokens,
        )

        (task_dir / "locator_analysis.json").write_text(
            json.dumps({
                "prompt_tokens": loc_resp.prompt_tokens,
                "completion_tokens": loc_resp.completion_tokens,
                "latency_seconds": loc_resp.latency_seconds,
                "analysis": locator_analysis,
            }, indent=2),
            encoding="utf-8",
        )

        supervisor_diagnosis = ""
        avoid_mistake = ""

        for attempt in range(1, self.max_attempts + 1):
            attempt_start = time.time()
            current_temperature = 0.0 if attempt == 1 else 0.2

            # Reset workspace to pristine state
            self.adapter.create_agent_workspace(task.task_id, ws_dir)

            # Build Coder prompt
            prompt_parts = [
                f"Fix the bug in the QuixBugs program '{prog_name}'.",
                f"Target file: {task.target_file}",
                f"\nSource code of '{task.target_file}':",
                f"```python\n{source_code}\n```",
                f"\n### FAULT LOCALIZATION ANALYSIS (Locator):\n{locator_analysis}\n",
            ]

            if attempt > 1:
                prompt_parts.append(f"\n### PREVIOUS ATTEMPT FAILED (Attempt {attempt - 1})")
                if last_eval_res:
                    prompt_parts.append(f"Failure Category: {last_eval_res.failure_category}")
                    if last_eval_res.sanitized_stdout:
                        prompt_parts.append(f"Sanitized Test Output:\n{last_eval_res.sanitized_stdout}")
                elif last_extract_error:
                    prompt_parts.append(f"Previous Patch Extraction Failure: {last_extract_error}")

                if last_candidate_diff:
                    prompt_parts.append(
                        f"\n### PREVIOUS FAILED CANDIDATE PATCH:\n```diff\n{last_candidate_diff.strip()}\n```\n"
                        f"CRITICAL: Do NOT propose this exact patch again! It failed evaluation.\n"
                    )

                if supervisor_diagnosis:
                    prompt_parts.append(f"### SUPERVISOR STRATEGIC GUIDANCE:\n{supervisor_diagnosis}\n")
                if avoid_mistake:
                    prompt_parts.append(f"### MISTAKE TO AVOID:\n{avoid_mistake}\n")

            full_prompt = "\n".join(prompt_parts)

            system_prompt = (
                "You are an expert Python Automated Program Repair agent. "
                "Output your response strictly as a JSON object conforming to this schema:\n"
                '{"reasoning_summary": "<concise explanation under 40 words>", "modifications": [{"path": "<file>", "operation": "replace", "anchor": "<exact line to replace>", "code": "<corrected line>"}]}'
            )

            # -----------------------------------------------------------------
            # Step 2: Coder Repair Generation (Ollama Local GPU)
            # -----------------------------------------------------------------
            coder_resp: ProviderResponse = self.coder_provider.generate(
                full_prompt,
                system_prompt=system_prompt,
                response_schema=CoderOutput,
                temperature=current_temperature,
            )

            p_tok = coder_resp.prompt_tokens or 0
            c_tok = coder_resp.completion_tokens or 0
            self.token_tracker.record(
                task_id=task.task_id,
                program_name=prog_name,
                attempt=attempt,
                role="Coder",
                provider=self.coder_provider_name,
                model=coder_resp.model_id,
                prompt_tokens=p_tok,
                completion_tokens=c_tok,
            )

            (task_dir / f"coder_raw_response_attempt_{attempt}.json").write_text(
                json.dumps({
                    "attempt": attempt,
                    "temperature": current_temperature,
                    "prompt_tokens": p_tok,
                    "completion_tokens": c_tok,
                    "latency_seconds": coder_resp.latency_seconds,
                    "raw_text": coder_resp.raw_text,
                    "parsed_json": coder_resp.parsed_json,
                }, indent=2),
                encoding="utf-8",
            )

            # Extract diff
            candidate_diff, extract_msg = self._extract_diff_from_response(task, coder_resp.raw_text, ws_dir)

            if not candidate_diff:
                dur = time.time() - attempt_start
                last_extract_error = extract_msg
                last_candidate_diff = ""
                history.append({
                    "attempt": attempt,
                    "temperature": current_temperature,
                    "patch_extracted": False,
                    "extraction_message": extract_msg,
                    "resolved": False,
                    "duration_seconds": round(dur, 3),
                })
                continue

            last_extract_error = ""
            last_candidate_diff = candidate_diff
            final_patch = candidate_diff

            # Anti-repetition check
            is_repeated = candidate_diff in seen_patches
            seen_patches.add(candidate_diff)

            # -----------------------------------------------------------------
            # Step 3: Tester Agent Pre-Critique (Tester: Groq Qwen)
            # -----------------------------------------------------------------
            self._check_budget_limits("Tester", "groq", est_tokens=2200)
            tester_prompt = (
                f"Evaluate this proposed patch for {prog_name}:\n"
                f"```diff\n{candidate_diff}\n```\n"
                f"Check for off-by-one errors, infinite loops, or syntax issues. "
                f"Keep your evaluation concise (under 100 words)."
            )
            tester_resp: ProviderResponse = self.tester_provider.generate(tester_prompt)

            if tester_resp.error_category == "RATE_LIMITED":
                raise RateLimitQuotaException(f"Tester (Groq) was rate-limited: {tester_resp.error}")

            handle_rate_limit_headers(tester_resp.rate_limit_headers, default_delay=self.pacing_delay)

            self.token_tracker.record(
                task_id=task.task_id,
                program_name=prog_name,
                attempt=attempt,
                role="Tester",
                provider="groq",
                model=tester_resp.model_id,
                prompt_tokens=tester_resp.prompt_tokens,
                completion_tokens=tester_resp.completion_tokens,
            )

            # -----------------------------------------------------------------
            # Step 4: Authoritative Evaluation in isolated sandbox
            # -----------------------------------------------------------------
            eval_res: QuixBugsEvaluationResult = self.adapter.evaluate_patch(
                ws_dir, task, candidate_diff, timeout=15
            )
            last_eval_res = eval_res
            dur = time.time() - attempt_start

            history.append({
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
            })

            if eval_res.resolved:
                is_resolved = True
                print(f"  [CLOUD_ASSISTED] SUCCESS: {prog_name} resolved on attempt {attempt}!")
                break

            # -----------------------------------------------------------------
            # Step 5: Supervisor Recovery Formulation (Groq Qwen)
            # -----------------------------------------------------------------
            if attempt < self.max_attempts:
                self._check_budget_limits("Supervisor", "groq", est_tokens=2600)
                sup_prompt = (
                    f"You are the Supervisor agent. The Coder proposed this patch which FAILED evaluation:\n"
                    f"```diff\n{candidate_diff}\n```\n"
                    f"Evaluation Outcome: {eval_res.evaluation_verdict}\n"
                    f"Failure Category: {eval_res.failure_category}\n"
                    f"Output / Trace:\n{eval_res.sanitized_stdout}\n"
                    f"Tester Critique:\n{tester_resp.raw_text}\n"
                    f"Is Repeated Patch: {is_repeated}\n\n"
                    f"Provide: 1) Strategic diagnosis of what went wrong. 2) Concrete mistake to avoid. "
                    f"Keep your response concise (under 100 words)."
                )
                sup_resp: ProviderResponse = self.supervisor_provider.generate(sup_prompt)

                if sup_resp.error_category == "RATE_LIMITED":
                    raise RateLimitQuotaException(f"Supervisor (Groq) was rate-limited: {sup_resp.error}")

                handle_rate_limit_headers(sup_resp.rate_limit_headers, default_delay=self.pacing_delay)

                self.token_tracker.record(
                    task_id=task.task_id,
                    program_name=prog_name,
                    attempt=attempt,
                    role="Supervisor",
                    provider="groq",
                    model=sup_resp.model_id,
                    prompt_tokens=sup_resp.prompt_tokens,
                    completion_tokens=sup_resp.completion_tokens,
                )

                supervisor_diagnosis = sup_resp.raw_text
                avoid_mistake = (
                    f"Do not propose the exact same patch again. "
                    f"Fix {eval_res.failure_category} identified by Supervisor."
                )

                # Insert failure record into isolated episodic memory
                rec = MemoryRecord(
                    task_id=task.task_id,
                    repository="quixbugs",
                    issue_summary=f"Attempt {attempt} failed with {eval_res.failure_category}",
                    failure_type=eval_res.failure_category,
                    diagnosis=supervisor_diagnosis[:500],
                    recovery_action=f"Re-prompt with supervisor guidance",
                    attempt=attempt,
                    result="FAILED",
                    relevant_files=[task.target_file],
                    agent="Coder",
                    metadata={
                        "is_repeated": is_repeated,
                        "failure_summary": eval_res.failure_summary,
                    },
                )
                self.mem_store.insert_record(rec)

        total_dur = round(time.time() - start_time, 3)

        # Save candidate patch diff
        (task_dir / "candidate_patch.diff").write_text(final_patch, encoding="utf-8")

        # Get granular token breakdown
        task_tokens = self.token_tracker.get_task_breakdown(task.task_id)

        result_payload = {
            "condition": "CLOUD_ASSISTED_DDIV",
            "task_id": task.task_id,
            "program_name": prog_name,
            "resolved": is_resolved,
            "attempts_used": len(history),
            "max_attempts": self.max_attempts,
            "total_tokens": task_tokens["total_tokens"],
            "prompt_tokens": task_tokens["prompt_tokens"],
            "completion_tokens": task_tokens["completion_tokens"],
            "token_breakdown": task_tokens,
            "total_duration_seconds": total_dur,
            "history": history,
        }
        (task_dir / "condition_result.json").write_text(
            json.dumps(result_payload, indent=2), encoding="utf-8"
        )
        return result_payload

    def run_all(self) -> Dict[str, Any]:
        """Execute repair across assigned tasks with checkpoint skipping and quota guards."""
        print("=" * 80)
        print("DDIV Phase 8.8.3: Cloud-Assisted Repair on QuixBugs Tasks")
        if self.batch:
            print(f"Batch Execution: Batch {self.batch} ({len(self.task_ids)} tasks)")
        else:
            print(f"Cohort Size: {len(self.task_ids)} tasks")
        print(f"Locator: {self.locator_provider.config.model_id} (Gemini)")
        print(f"Supervisor: {self.supervisor_provider.config.model_id} (Groq)")
        print(f"Tester: {self.tester_provider.config.model_id} (Groq)")
        print(f"Coder: {self.coder_provider.config.model_id} ({self.coder_provider_name.upper()})")
        print(f"Output Directory: {self.output_dir}")
        print(f"Daily Groq Token Budget Ceiling: {self.max_daily_groq_tokens}")
        print(f"Daily Gemini Token Budget Ceiling: {self.max_daily_gemini_tokens}")
        print("=" * 80)

        all_results = {}
        resolved_count = 0
        skipped_count = 0
        halt_reason = "COMPLETED"

        for i, t_info in enumerate(self.manifest_tasks, 1):
            t_id = t_info["canonical_task_id"]
            p_name = t_info["program_name"]
            result_file = self.output_dir / p_name / "condition_result.json"

            # -----------------------------------------------------------------
            # Safe Checkpoint / Resume Verification
            # -----------------------------------------------------------------
            is_valid, cached_res, reason = validate_checkpoint_result(
                result_file, t_id, p_name, self.max_attempts
            )
            if is_valid and cached_res:
                print(f"[{i}/{len(self.manifest_tasks)}] CHECKPOINT SKIP: {p_name} ({t_id}) — {reason}")
                all_results[p_name] = cached_res
                skipped_count += 1
                if cached_res.get("resolved"):
                    resolved_count += 1
                continue
            elif result_file.exists():
                print(f"[{i}/{len(self.manifest_tasks)}] CHECKPOINT RE-RUN: {p_name} ({t_id}) — Prior result invalid: {reason}")
            else:
                print(f"\n[{i}/{len(self.manifest_tasks)}] TASK START: {p_name} ({t_id})")

            # Check daily quota budgets before starting next task
            try:
                self._check_budget_limits("Supervisor", "groq", est_tokens=4000)
                self._check_budget_limits("Locator", "gemini", est_tokens=2000)
            except RateLimitQuotaException as qe:
                print(f"\n[QUOTA BUDGET GUARD] Halting run before task {p_name}: {qe}")
                halt_reason = "STOPPED_DAILY_BUDGET_REACHED"
                break

            task_obj = self.adapter.get_task(t_id)
            if not task_obj:
                print(f"ERROR: Could not load task {t_id}")
                continue

            try:
                res = self.run_task(task_obj)
                all_results[p_name] = res
                if res.get("resolved"):
                    resolved_count += 1
                # Persist cumulative token usage after each task
                self.token_tracker.persist()
            except RateLimitQuotaException as rqe:
                print(f"\n[QUOTA HALT] Task {p_name} aborted due to rate limit/quota ceiling: {rqe}")
                halt_reason = "STOPPED_QUOTA_EXHAUSTED"
                # Do NOT write partial/corrupt condition_result.json
                self.token_tracker.persist()
                break

        today_str = time.strftime("%Y-%m-%d", time.gmtime())
        summary = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "status": halt_reason,
            "batch": self.batch,
            "total_assigned_tasks": len(self.task_ids),
            "completed_tasks": len(all_results),
            "skipped_checkpoint_tasks": skipped_count,
            "resolved": resolved_count,
            "resolution_rate_pct": (
                round(resolved_count / len(all_results) * 100, 2) if all_results else 0.0
            ),
            "today_date_utc": today_str,
            "today_groq_tokens": self.token_tracker.get_daily_provider_total("groq", today_str),
            "today_gemini_tokens": self.token_tracker.get_daily_provider_total("gemini", today_str),
            "cumulative_groq_tokens": self.token_tracker.cumulative_by_provider.get("groq", {}).get("total", 0),
            "cumulative_gemini_tokens": self.token_tracker.cumulative_by_provider.get("gemini", {}).get("total", 0),
            "current_session_groq_tokens": self.token_tracker.get_session_provider_total("groq"),
            "current_session_gemini_tokens": self.token_tracker.get_session_provider_total("gemini"),
            "results": all_results,
        }
        if self.batch:
            (self.output_dir / f"quixbugs_cloud_assisted_summary_batch_{self.batch}.json").write_text(
                json.dumps(summary, indent=2), encoding="utf-8"
            )

        # Update master summary across all batches
        master_results = {}
        for sub in self.output_dir.iterdir():
            if sub.is_dir():
                cond_file = sub / "condition_result.json"
                if cond_file.exists():
                    try:
                        cr_data = json.loads(cond_file.read_text(encoding="utf-8"))
                        master_results[sub.name] = cr_data
                    except Exception:
                        pass

        master_resolved = sum(1 for r in master_results.values() if r.get("resolved"))
        master_summary = dict(summary)
        master_summary["batch"] = "all"
        master_summary["total_assigned_tasks"] = 27
        master_summary["completed_tasks"] = len(master_results)
        master_summary["resolved"] = master_resolved
        master_summary["resolution_rate_pct"] = (
            round(master_resolved / len(master_results) * 100, 2) if master_results else 0.0
        )
        master_summary["results"] = master_results

        (self.output_dir / "quixbugs_cloud_assisted_summary.json").write_text(
            json.dumps(master_summary, indent=2), encoding="utf-8"
        )
        self.token_tracker.persist()
        return summary


def main():
    parser = argparse.ArgumentParser(description="Run Cloud-Assisted DDIV Repair on Unresolved QuixBugs Tasks")
    parser.add_argument(
        "--task-manifest",
        type=str,
        default="results/quixbugs_cloud_assisted_preflight_20261016T092253Z/unresolved_task_manifest.json",
        help="Path to unresolved tasks JSON manifest",
    )
    parser.add_argument(
        "--batch-manifest",
        type=str,
        default="results/quixbugs_cloud_assisted_preflight_20261016T092253Z/three_day_batch_manifest.json",
        help="Path to 3-day batch manifest JSON",
    )
    parser.add_argument(
        "--batch",
        type=int,
        choices=[1, 2, 3],
        default=None,
        help="Execute specific batch: 1 (Tasks 1-9), 2 (Tasks 10-18), or 3 (Tasks 19-27)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        required=True,
        help="Dedicated output directory for cloud-assisted repair experiment",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=3,
        help="Maximum repair attempts per task (default: 3)",
    )
    parser.add_argument(
        "--coder-provider",
        type=str,
        default="ollama",
        choices=["ollama", "groq"],
        help="Provider for Coder agent: 'ollama' (Option A: local 7B, default) or 'groq' (Option B: cloud 120B)",
    )
    parser.add_argument(
        "--max-daily-groq-tokens",
        type=int,
        default=100000,
        help="Daily conservative ceiling for Groq tokens (default: 100000)",
    )
    parser.add_argument(
        "--max-daily-gemini-tokens",
        type=int,
        default=30000,
        help="Daily conservative ceiling for Gemini tokens (default: 30000)",
    )
    parser.add_argument(
        "--pacing-delay",
        type=float,
        default=10.0,
        help="Pacing sleep in seconds between consecutive cloud calls to respect TPM limits",
    )

    args = parser.parse_args()

    runner = QuixBugsCloudAssistedRunner(
        task_manifest_path=args.task_manifest,
        output_dir=args.output_dir,
        max_attempts=args.max_attempts,
        coder_provider=args.coder_provider,
        batch=args.batch,
        batch_manifest_path=args.batch_manifest,
        max_daily_groq_tokens=args.max_daily_groq_tokens,
        max_daily_gemini_tokens=args.max_daily_gemini_tokens,
        pacing_delay=args.pacing_delay,
    )
    runner.run_all()


if __name__ == "__main__":
    main()
