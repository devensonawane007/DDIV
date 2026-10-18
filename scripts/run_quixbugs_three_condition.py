#!/usr/bin/env python3
"""
DDIV Phase 8.9.3: Three-Condition Comparative Evaluation Runner for QuixBugs.

Supports:
1. BASELINE: 1 attempt, local Ollama Coder, supervisory/feedback mechanisms disabled.
2. RETRY_ONLY: Up to 3 attempts, local Ollama Coder, sanitized pytest diagnostics, no supervisor/memory/trust.
3. FULL_DDIV: Up to 3 attempts, Option A Hybrid (Gemini Locator, Groq Supervisor/Tester, Ollama Coder),
             episodic memory, FailureDetector, Tester pre-critique, and anti-repetition gate.

Strictly protects historical results and production database (data/ddiv_memory.db).
Reuses verified Batch 1 FULL_DDIV results through manifest metadata references without rerun.
"""

import argparse
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

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

from evaluation.quixbugs_adapter import (
    QuixBugsAdapter,
    QuixBugsTask,
    QuixBugsEvaluationResult,
    sanitize_evaluator_output,
)
from scripts.ollama_coder_adapter import OllamaProvider, robust_extract_json
from models.base import ModelConfig, ProviderResponse
from models.providers import GeminiProvider, GroqProvider, ErrorCategory
from scripts.demo_patch_builder import DemoPatchBuilder
from memory.memory_store import MemoryStore
from memory.schemas import MemoryRecord
from agents.coder import CoderOutput


class RateLimitQuotaException(Exception):
    """Raised when an API rate limit or daily token ceiling is encountered."""
    pass


def parse_header_duration(duration_str: str) -> float:
    """Parses duration strings like '2s', '500ms', '1m' into seconds."""
    if not duration_str:
        return 0.0
    s = duration_str.strip().lower()
    if s.endswith("ms"):
        try:
            return float(s[:-2]) / 1000.0
        except ValueError:
            return 0.0
    elif s.endswith("s"):
        try:
            return float(s[:-1])
        except ValueError:
            return 0.0
    elif s.endswith("m"):
        try:
            return float(s[:-1]) * 60.0
        except ValueError:
            return 0.0
    try:
        return float(s)
    except ValueError:
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
    expected_condition: Optional[str] = None,
) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    """
    Authoritative validation of existing condition_result.json.
    Returns (is_valid, parsed_result, reason).
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

    cond_in_file = data.get("condition")
    if expected_condition:
        valid_conditions = [expected_condition.upper()]
        if expected_condition.upper() == "FULL_DDIV":
            valid_conditions.append("CLOUD_ASSISTED_DDIV")
        if cond_in_file.upper() not in valid_conditions:
            return False, None, f"Mismatched condition: expected {valid_conditions}, got {cond_in_file}"

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
        diff_file = result_path.parent / "candidate_patch.diff"
        if not diff_file.exists():
            return False, None, "Resolved result missing candidate_patch.diff"
        return True, data, "Valid resolved task"

    if attempts_used < max_attempts:
        return (
            False,
            None,
            f"Partial/interrupted failure: completed {attempts_used}/{max_attempts} attempts",
        )

    return True, data, f"Valid authoritative failure ({attempts_used}/{max_attempts} attempts)"


class CumulativeTokenTracker:
    """Tracks token usage across providers, roles, conditions, tasks, and process restarts."""

    def __init__(self, persistence_path: Optional[Path] = None):
        self.persistence_path = Path(persistence_path) if persistence_path else None
        self.transactions: List[Dict[str, Any]] = []

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
        self.session_by_condition: Dict[str, Dict[str, int]] = {
            "BASELINE": {"prompt": 0, "completion": 0, "total": 0},
            "RETRY_ONLY": {"prompt": 0, "completion": 0, "total": 0},
            "FULL_DDIV": {"prompt": 0, "completion": 0, "total": 0},
        }

        self.usage_by_date: Dict[str, Dict[str, Dict[str, int]]] = {}
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
        self.cumulative_by_condition: Dict[str, Dict[str, int]] = {
            "BASELINE": {"prompt": 0, "completion": 0, "total": 0},
            "RETRY_ONLY": {"prompt": 0, "completion": 0, "total": 0},
            "FULL_DDIV": {"prompt": 0, "completion": 0, "total": 0},
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

            for c, counts in data.get("totals_by_condition", {}).items():
                if c not in self.cumulative_by_condition:
                    self.cumulative_by_condition[c] = {"prompt": 0, "completion": 0, "total": 0}
                self.cumulative_by_condition[c]["prompt"] = counts.get("prompt", 0)
                self.cumulative_by_condition[c]["completion"] = counts.get("completion", 0)
                self.cumulative_by_condition[c]["total"] = counts.get("total", 0)

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
        condition: str = "FULL_DDIV",
    ):
        p_name = provider.lower()
        cond_name = condition.upper()
        tot = prompt_tokens + completion_tokens
        today_str = time.strftime("%Y-%m-%d", time.gmtime())

        tx = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "date_utc": today_str,
            "task_id": task_id,
            "program_name": program_name,
            "condition": cond_name,
            "attempt": attempt,
            "role": role,
            "provider": p_name,
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": tot,
        }
        self.transactions.append(tx)

        if p_name in self.session_by_provider:
            self.session_by_provider[p_name]["prompt"] += prompt_tokens
            self.session_by_provider[p_name]["completion"] += completion_tokens
            self.session_by_provider[p_name]["total"] += tot

        if role in self.session_by_role:
            self.session_by_role[role]["prompt"] += prompt_tokens
            self.session_by_role[role]["completion"] += completion_tokens
            self.session_by_role[role]["total"] += tot

        if cond_name in self.session_by_condition:
            self.session_by_condition[cond_name]["prompt"] += prompt_tokens
            self.session_by_condition[cond_name]["completion"] += completion_tokens
            self.session_by_condition[cond_name]["total"] += tot

        if today_str not in self.usage_by_date:
            self.usage_by_date[today_str] = {}
        if p_name not in self.usage_by_date[today_str]:
            self.usage_by_date[today_str][p_name] = {"prompt": 0, "completion": 0, "total": 0}
        self.usage_by_date[today_str][p_name]["prompt"] += prompt_tokens
        self.usage_by_date[today_str][p_name]["completion"] += completion_tokens
        self.usage_by_date[today_str][p_name]["total"] += tot

        if p_name in self.cumulative_by_provider:
            self.cumulative_by_provider[p_name]["prompt"] += prompt_tokens
            self.cumulative_by_provider[p_name]["completion"] += completion_tokens
            self.cumulative_by_provider[p_name]["total"] += tot

        if role in self.cumulative_by_role:
            self.cumulative_by_role[role]["prompt"] += prompt_tokens
            self.cumulative_by_role[role]["completion"] += completion_tokens
            self.cumulative_by_role[role]["total"] += tot

        if cond_name in self.cumulative_by_condition:
            self.cumulative_by_condition[cond_name]["prompt"] += prompt_tokens
            self.cumulative_by_condition[cond_name]["completion"] += completion_tokens
            self.cumulative_by_condition[cond_name]["total"] += tot

    def get_daily_provider_total(self, provider: str, date_str: str) -> int:
        p_name = provider.lower()
        if date_str in self.usage_by_date and p_name in self.usage_by_date[date_str]:
            return self.usage_by_date[date_str][p_name].get("total", 0)
        return 0

    def get_session_provider_total(self, provider: str) -> int:
        p_name = provider.lower()
        return self.session_by_provider.get(p_name, {}).get("total", 0)

    def persist(self):
        if not self.persistence_path:
            return
        self.persistence_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "last_updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "session_count": self.session_count,
            "usage_by_date": self.usage_by_date,
            "totals_by_provider": self.cumulative_by_provider,
            "totals_by_role": self.cumulative_by_role,
            "totals_by_condition": self.cumulative_by_condition,
            "grand_total_tokens": sum(p["total"] for p in self.cumulative_by_provider.values()),
            "current_session_provider_tokens": self.session_by_provider,
            "current_session_role_tokens": self.session_by_role,
            "current_session_condition_tokens": self.session_by_condition,
        }
        self.persistence_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


class QuixBugsThreeConditionRunner:
    """Unified runner for BASELINE, RETRY_ONLY, and FULL_DDIV conditions."""

    def __init__(
        self,
        manifest_path: str,
        output_dir: str,
        condition: str = "ALL",
        batch: Optional[int] = None,
        max_attempts: int = 3,
        coder_provider: str = "ollama",
        max_daily_groq_tokens: int = 100000,
        max_daily_gemini_tokens: int = 30000,
        pacing_delay: float = 15.0,
        coder_provider_instance: Optional[Any] = None,
        locator_provider_instance: Optional[Any] = None,
        supervisor_provider_instance: Optional[Any] = None,
        tester_provider_instance: Optional[Any] = None,
    ):
        self.manifest_path = Path(manifest_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.condition_filter = condition.upper()
        self.batch = batch
        self.max_attempts = max_attempts
        self.coder_provider_name = coder_provider.lower()
        self.max_daily_groq_tokens = max_daily_groq_tokens
        self.max_daily_gemini_tokens = max_daily_gemini_tokens
        self.pacing_delay = pacing_delay

        self.adapter = QuixBugsAdapter()

        # Load run manifest
        if not self.manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found: {self.manifest_path}")

        manifest_raw = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        all_obs = manifest_raw.get("observations", [])

        # Filter observations by batch and condition
        self.observations = []
        for o in all_obs:
            if self.batch is not None and o.get("batch_number") != self.batch:
                continue
            if self.condition_filter != "ALL" and o.get("condition") != self.condition_filter:
                continue
            self.observations.append(o)

        # Setup Token Tracker
        self.token_tracker = CumulativeTokenTracker(
            persistence_path=self.output_dir / "cumulative_token_usage.json"
        )

        # Setup isolated episodic memory for FULL_DDIV
        self.full_ddiv_memory_db = self.output_dir / "full_ddiv_memory.db"
        self._initialize_full_ddiv_memory_lineage()

        # Initialize Providers
        # Coder (always Ollama for option A)
        if coder_provider_instance is not None:
            self.coder_provider = coder_provider_instance
        else:
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

        # Cloud agents initialized only if FULL_DDIV is active
        self.locator_provider = None
        self.supervisor_provider = None
        self.tester_provider = None

        if self.condition_filter in ("FULL_DDIV", "ALL"):
            if locator_provider_instance is not None:
                self.locator_provider = locator_provider_instance
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

            if supervisor_provider_instance is not None:
                self.supervisor_provider = supervisor_provider_instance
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

            if tester_provider_instance is not None:
                self.tester_provider = tester_provider_instance
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

    def _initialize_full_ddiv_memory_lineage(self):
        """Preserve continuous memory lineage from completed Batch 1 FULL_DDIV if starting fresh."""
        if not self.full_ddiv_memory_db.exists():
            seed_db = Path("results/quixbugs_cloud_assisted_repair_20261016T100000Z/quixbugs_cloud_assisted_memory.db")
            if seed_db.exists():
                shutil.copy2(seed_db, self.full_ddiv_memory_db)
                print(f"[MEMORY INIT] Seeded continuous FULL_DDIV memory from {seed_db}")
            else:
                self.mem_store = MemoryStore(db_path=self.full_ddiv_memory_db)
        self.mem_store = MemoryStore(db_path=self.full_ddiv_memory_db)

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

    def import_reused_full_ddiv_result(self, obs: Dict[str, Any]) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """
        Safely imports an existing validated FULL_DDIV result through manifest metadata references.
        Does not rerun inference or consume any cloud tokens.
        """
        prog_name = obs["program_name"]
        t_id = obs["canonical_task_id"]
        source_dir_str = obs.get("reuse_source")
        if not source_dir_str:
            return False, None, "No reuse_source specified in observation"

        source_dir = Path(source_dir_str)
        src_task_dir = source_dir / prog_name
        src_res_file = src_task_dir / "condition_result.json"

        # Strict validation before reuse
        is_valid, data, reason = validate_checkpoint_result(
            src_res_file, t_id, prog_name, max_attempts=3, expected_condition="FULL_DDIV"
        )
        if not is_valid or not data:
            return False, None, f"Source result validation failed: {reason}"

        # Destination in comparative output directory
        dest_dir = self.output_dir / "full_ddiv" / prog_name
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Copy artifacts without mutating historical source
        dest_res_file = dest_dir / "condition_result.json"
        dest_res_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

        for f_name in ["candidate_patch.diff", "locator_analysis.json"]:
            s_f = src_task_dir / f_name
            if s_f.exists():
                shutil.copy2(s_f, dest_dir / f_name)

        for raw_f in src_task_dir.glob("coder_raw_response_attempt_*.json"):
            shutil.copy2(raw_f, dest_dir / raw_f.name)

        # Record tokens in tracker without adding to daily usage
        tb = data.get("token_breakdown", {})
        for tx in tb.get("transactions", []):
            self.token_tracker.transactions.append(tx)

        return True, data, "Reused completed result imported successfully"

    def run_task_condition(self, task: QuixBugsTask, condition: str) -> Dict[str, Any]:
        """Execute repair for one task under one condition."""
        cond_upper = condition.upper()
        prog_name = task.program_name
        cond_dir = self.output_dir / cond_upper.lower() / prog_name
        cond_dir.mkdir(parents=True, exist_ok=True)
        ws_dir = cond_dir / "workspace"

        # Initialize clean isolated workspace
        self.adapter.create_agent_workspace(task.task_id, ws_dir)

        max_att = 1 if cond_upper == "BASELINE" else 3
        history: List[Dict[str, Any]] = []
        is_resolved = False
        seen_patches: Set[str] = set()
        final_patch = ""

        start_time = time.time()
        last_candidate_diff = ""
        last_eval_res: Optional[QuixBugsEvaluationResult] = None
        last_extract_error = ""

        prog_file = ws_dir / task.target_file
        source_code = prog_file.read_text(encoding="utf-8") if prog_file.exists() else ""

        # Fault Localization (Only for FULL_DDIV)
        locator_analysis = ""
        if cond_upper == "FULL_DDIV":
            self._check_budget_limits("Locator", "gemini", est_tokens=2000)
            loc_prompt = (
                f"You are an expert Fault Localization agent. Analyze the following Python program from QuixBugs:\n\n"
                f"Program File: {task.target_file}\n"
                f"```python\n{source_code}\n```\n\n"
                f"Identify the exact buggy line(s), explain the algorithmic flaw, and specify which lines must be modified."
            )
            loc_resp: ProviderResponse = self.locator_provider.generate(loc_prompt)

            if loc_resp.error_category == "RATE_LIMITED":
                raise RateLimitQuotaException(f"Locator (Gemini) was rate-limited: {loc_resp.error}")

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
                condition=cond_upper,
            )

            (cond_dir / "locator_analysis.json").write_text(
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

        for attempt in range(1, max_att + 1):
            attempt_start = time.time()
            current_temperature = 0.0 if (attempt == 1 or cond_upper == "BASELINE") else 0.2

            # Reset workspace to pristine state
            self.adapter.create_agent_workspace(task.task_id, ws_dir)

            # Build prompt according to condition specification
            prompt_parts = [
                f"Fix the bug in the QuixBugs program '{prog_name}'.",
                f"Target file: {task.target_file}",
            ]

            if cond_upper in ("BASELINE", "RETRY_ONLY"):
                prompt_parts.append(f"### PROBLEM SPECIFICATION:\n{task.problem_description}\n")

            prompt_parts.append(f"Source code of '{task.target_file}':\n```python\n{source_code}\n```\n")

            if cond_upper == "FULL_DDIV" and locator_analysis:
                prompt_parts.append(f"### FAULT LOCALIZATION ANALYSIS (Locator):\n{locator_analysis}\n")

            if attempt > 1 and cond_upper in ("RETRY_ONLY", "FULL_DDIV"):
                prompt_parts.append(f"### PREVIOUS ATTEMPT FAILED (Attempt {attempt - 1})")
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

                if cond_upper == "FULL_DDIV":
                    if supervisor_diagnosis:
                        prompt_parts.append(f"### SUPERVISOR STRATEGIC GUIDANCE:\n{supervisor_diagnosis}\n")
                    if avoid_mistake:
                        prompt_parts.append(f"### MISTAKE TO AVOID:\n{avoid_mistake}\n")

            full_prompt = "\n".join(prompt_parts)

            system_prompt = (
                "You are an expert Python Automated Program Repair agent. "
                "Output your response strictly as a JSON object conforming to this schema:\n"
                '{"reasoning_summary": "<concise explanation under 40 words>", '
                '"modifications": [{"path": "<file>", "operation": "replace", "anchor": "<exact line to replace>", "code": "<corrected line>"}]}'
            )

            # Coder Generation (Local Ollama for all conditions)
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
                condition=cond_upper,
            )

            (cond_dir / f"coder_raw_response_attempt_{attempt}.json").write_text(
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

            is_repeated = candidate_diff in seen_patches
            seen_patches.add(candidate_diff)

            # Tester Pre-Critique (Only for FULL_DDIV)
            tester_critique = ""
            if cond_upper == "FULL_DDIV":
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
                tester_critique = tester_resp.raw_text

                self.token_tracker.record(
                    task_id=task.task_id,
                    program_name=prog_name,
                    attempt=attempt,
                    role="Tester",
                    provider="groq",
                    model=tester_resp.model_id,
                    prompt_tokens=tester_resp.prompt_tokens,
                    completion_tokens=tester_resp.completion_tokens,
                    condition=cond_upper,
                )

            # Authoritative Evaluation in isolated sandbox
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
                print(f"  [{cond_upper}] SUCCESS: {prog_name} resolved on attempt {attempt}!")
                break

            # Supervisor Recovery Guidance (Only for FULL_DDIV)
            if cond_upper == "FULL_DDIV" and attempt < max_att:
                self._check_budget_limits("Supervisor", "groq", est_tokens=2600)
                sup_prompt = (
                    f"You are the Supervisor agent. The Coder proposed this patch which FAILED evaluation:\n"
                    f"```diff\n{candidate_diff}\n```\n"
                    f"Evaluation Outcome: {eval_res.evaluation_verdict}\n"
                    f"Failure Category: {eval_res.failure_category}\n"
                    f"Output / Trace:\n{eval_res.sanitized_stdout}\n"
                    f"Tester Critique:\n{tester_critique}\n"
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
                    condition=cond_upper,
                )

                supervisor_diagnosis = sup_resp.raw_text
                avoid_mistake = (
                    f"Do not propose the exact same patch again. "
                    f"Fix {eval_res.failure_category} identified by Supervisor."
                )

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

        # Build task condition result
        total_duration = time.time() - start_time
        task_txs = [
            tx for tx in self.token_tracker.transactions
            if tx.get("task_id") == task.task_id and tx.get("condition") == cond_upper
        ]
        task_prompt_tokens = sum(tx.get("prompt_tokens", 0) for tx in task_txs)
        task_comp_tokens = sum(tx.get("completion_tokens", 0) for tx in task_txs)
        task_total_tokens = task_prompt_tokens + task_comp_tokens

        role_breakdown: Dict[str, Dict[str, int]] = {}
        provider_breakdown: Dict[str, Dict[str, int]] = {}

        for tx in task_txs:
            r = tx.get("role")
            p = tx.get("provider")
            if r not in role_breakdown:
                role_breakdown[r] = {"prompt": 0, "completion": 0, "total": 0}
            role_breakdown[r]["prompt"] += tx.get("prompt_tokens", 0)
            role_breakdown[r]["completion"] += tx.get("completion_tokens", 0)
            role_breakdown[r]["total"] += tx.get("total_tokens", 0)

            if p not in provider_breakdown:
                provider_breakdown[p] = {"prompt": 0, "completion": 0, "total": 0}
            provider_breakdown[p]["prompt"] += tx.get("prompt_tokens", 0)
            provider_breakdown[p]["completion"] += tx.get("completion_tokens", 0)
            provider_breakdown[p]["total"] += tx.get("total_tokens", 0)

        result_payload = {
            "condition": cond_upper,
            "task_id": task.task_id,
            "program_name": prog_name,
            "resolved": is_resolved,
            "attempts_used": len(history),
            "max_attempts": max_att,
            "total_tokens": task_total_tokens,
            "prompt_tokens": task_prompt_tokens,
            "completion_tokens": task_comp_tokens,
            "token_breakdown": {
                "total_tokens": task_total_tokens,
                "prompt_tokens": task_prompt_tokens,
                "completion_tokens": task_comp_tokens,
                "by_role": role_breakdown,
                "by_provider": provider_breakdown,
                "transactions": task_txs,
            },
            "total_duration_seconds": round(total_duration, 3),
            "history": history,
        }

        # Save result JSON and diff artifact
        (cond_dir / "condition_result.json").write_text(
            json.dumps(result_payload, indent=2), encoding="utf-8"
        )
        if final_patch:
            (cond_dir / "candidate_patch.diff").write_text(final_patch, encoding="utf-8")

        return result_payload

    def run_all(self) -> Dict[str, Any]:
        """Execute repair across assigned observations with checkpoint skipping and quota guards."""
        print("=" * 80)
        print("DDIV Phase 8.9.3: Three-Condition Comparative Repair Runner")
        print(f"Condition Filter: {self.condition_filter}")
        print(f"Batch Filter: Batch {self.batch}" if self.batch else "Batch Filter: All Batches")
        print(f"Assigned Observations: {len(self.observations)}")
        print(f"Output Directory: {self.output_dir}")
        print(f"Daily Groq Ceiling: {self.max_daily_groq_tokens}")
        print(f"Daily Gemini Ceiling: {self.max_daily_gemini_tokens}")
        print("=" * 80)

        all_results: Dict[str, Dict[str, Any]] = {}
        resolved_count = 0
        skipped_count = 0
        reused_count = 0
        halt_reason = "COMPLETED"

        for i, obs in enumerate(self.observations, 1):
            t_id = obs["canonical_task_id"]
            p_name = obs["program_name"]
            cond = obs["condition"].upper()
            obs_id = obs.get("observation_id", f"OBS-{i:02d}")
            result_file = self.output_dir / cond.lower() / p_name / "condition_result.json"

            # 1. Reused Completed Import Check
            if obs.get("status") == "REUSED_COMPLETED":
                is_imported, cached_res, reason = self.import_reused_full_ddiv_result(obs)
                if is_imported and cached_res:
                    print(f"[{i}/{len(self.observations)}] {obs_id} REUSED IMPORT: {p_name} ({cond}) — {reason}")
                    if cond not in all_results:
                        all_results[cond] = {}
                    all_results[cond][p_name] = cached_res
                    reused_count += 1
                    if cached_res.get("resolved"):
                        resolved_count += 1
                    continue
                else:
                    print(f"[{i}/{len(self.observations)}] {obs_id} REUSE FAILED: {p_name} ({cond}) — {reason}; falling back to execution")

            # 2. Checkpoint Skip Check
            max_att = 1 if cond == "BASELINE" else 3
            is_valid, cached_res, reason = validate_checkpoint_result(
                result_file, t_id, p_name, max_att, expected_condition=cond
            )
            if is_valid and cached_res:
                print(f"[{i}/{len(self.observations)}] {obs_id} CHECKPOINT SKIP: {p_name} ({cond}) — {reason}")
                if cond not in all_results:
                    all_results[cond] = {}
                all_results[cond][p_name] = cached_res
                skipped_count += 1
                if cached_res.get("resolved"):
                    resolved_count += 1
                continue
            elif result_file.exists():
                print(f"[{i}/{len(self.observations)}] {obs_id} CHECKPOINT RE-RUN: {p_name} ({cond}) — Prior invalid: {reason}")
            else:
                print(f"\n[{i}/{len(self.observations)}] {obs_id} OBSERVATION START: {p_name} ({cond})")

            # 3. Quota check for cloud conditions
            if cond == "FULL_DDIV":
                try:
                    self._check_budget_limits("Supervisor", "groq", est_tokens=4000)
                    self._check_budget_limits("Locator", "gemini", est_tokens=2000)
                except RateLimitQuotaException as qe:
                    print(f"\n[QUOTA BUDGET GUARD] Halting run before {p_name} ({cond}): {qe}")
                    halt_reason = "STOPPED_DAILY_BUDGET_REACHED"
                    break

            task_obj = self.adapter.get_task(t_id)
            if not task_obj:
                print(f"ERROR: Could not load task {t_id}")
                continue

            try:
                res = self.run_task_condition(task_obj, cond)
                if cond not in all_results:
                    all_results[cond] = {}
                all_results[cond][p_name] = res
                if res.get("resolved"):
                    resolved_count += 1
                self.token_tracker.persist()
            except RateLimitQuotaException as rqe:
                print(f"\n[QUOTA HALT] Task {p_name} ({cond}) aborted due to quota/rate limit: {rqe}")
                halt_reason = "STOPPED_QUOTA_EXHAUSTED"
                self.token_tracker.persist()
                break

        # Generate Summaries
        today_str = time.strftime("%Y-%m-%d", time.gmtime())
        total_completed = sum(len(cond_dict) for cond_dict in all_results.values())

        summary = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "status": halt_reason,
            "condition_filter": self.condition_filter,
            "batch": self.batch,
            "total_assigned_observations": len(self.observations),
            "completed_observations": total_completed,
            "skipped_checkpoint_observations": skipped_count,
            "reused_observations": reused_count,
            "resolved": resolved_count,
            "resolution_rate_pct": (
                round(resolved_count / total_completed * 100, 2) if total_completed else 0.0
            ),
            "today_date_utc": today_str,
            "today_groq_tokens": self.token_tracker.get_daily_provider_total("groq", today_str),
            "today_gemini_tokens": self.token_tracker.get_daily_provider_total("gemini", today_str),
            "cumulative_groq_tokens": self.token_tracker.cumulative_by_provider.get("groq", {}).get("total", 0),
            "cumulative_gemini_tokens": self.token_tracker.cumulative_by_provider.get("gemini", {}).get("total", 0),
            "results_by_condition": all_results,
        }

        # Save summary JSON
        summary_filename = (
            f"quixbugs_three_condition_summary_batch_{self.batch}.json"
            if self.batch else "quixbugs_three_condition_summary.json"
        )
        (self.output_dir / summary_filename).write_text(json.dumps(summary, indent=2), encoding="utf-8")
        self.token_tracker.persist()
        return summary


def main():
    parser = argparse.ArgumentParser(description="Run Three-Condition Comparative Repair on QuixBugs Tasks")
    parser.add_argument(
        "--manifest",
        type=str,
        default="results/quixbugs_three_condition_manifests_20261016T120000Z/three_condition_run_manifest.json",
        help="Path to 3-condition run manifest JSON",
    )
    parser.add_argument(
        "--condition",
        type=str,
        choices=["BASELINE", "RETRY_ONLY", "FULL_DDIV", "ALL"],
        default="ALL",
        help="Condition to evaluate: 'BASELINE', 'RETRY_ONLY', 'FULL_DDIV', or 'ALL' (default: ALL)",
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
        default="results/quixbugs_three_condition_eval_20261016T120000Z",
        help="Dedicated output directory for comparative evaluation",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=3,
        help="Maximum repair attempts per task for multi-attempt conditions (default: 3)",
    )
    parser.add_argument(
        "--coder-provider",
        type=str,
        default="ollama",
        choices=["ollama"],
        help="Provider for Coder agent (default: 'ollama')",
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
        default=15.0,
        help="Pacing delay in seconds between consecutive cloud calls (default: 15.0)",
    )

    args = parser.parse_args()

    runner = QuixBugsThreeConditionRunner(
        manifest_path=args.manifest,
        output_dir=args.output_dir,
        condition=args.condition,
        batch=args.batch,
        max_attempts=args.max_attempts,
        coder_provider=args.coder_provider,
        max_daily_groq_tokens=args.max_daily_groq_tokens,
        max_daily_gemini_tokens=args.max_daily_gemini_tokens,
        pacing_delay=args.pacing_delay,
    )
    runner.run_all()


if __name__ == "__main__":
    main()
