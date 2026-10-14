"""Isolated child worker process for DDIV Coder Model Ablation.

Executes a single (task, coder_variant) repair under FULL_DDIV inside an isolated workspace.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import traceback
from pathlib import Path

# Ensure project root is in sys.path
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from dotenv import load_dotenv
load_dotenv(Path(project_root) / ".env", override=True)

from core.conditions import ExperimentCondition
from core.config import AgentModelConfig, DDIVConfig, ExecutionMode, ProviderType
from core.experiment_worker import ExperimentWorker


class LoggerWriter:
    """Tee writer sending output to both original stream and a log file."""

    def __init__(self, original_stream, log_file_path: Path):
        if original_stream is not None and hasattr(original_stream, "reconfigure"):
            try:
                original_stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
        self.original_stream = original_stream
        self.log_file_path = log_file_path
        self.log_file_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_file = open(self.log_file_path, "a", encoding="utf-8", buffering=1)

    def write(self, message):
        if self.original_stream is not None:
            try:
                self.original_stream.write(message)
            except UnicodeEncodeError:
                encoding = getattr(self.original_stream, "encoding", None) or "utf-8"
                safe_msg = message.encode(encoding, errors="replace").decode(encoding)
                self.original_stream.write(safe_msg)
            except Exception:
                pass
        self.log_file.write(message)

    def flush(self):
        if self.original_stream is not None and hasattr(self.original_stream, "flush"):
            try:
                self.original_stream.flush()
            except Exception:
                pass
        self.log_file.flush()

    def close(self):
        try:
            self.log_file.close()
        except Exception:
            pass


def create_ablation_config(coder_variant: str, provider: str) -> DDIVConfig:
    """Construct an isolated DDIVConfig overriding strictly the Coder agent."""
    config = DDIVConfig.load_from_env()

    if provider == "real":
        config.mode = ExecutionMode.DDIV
        config.provider_type = ProviderType.OPENAI_COMPATIBLE

        if coder_variant == "coder_b":
            # Treatment: Gemini 3.8 Flash
            config.coder = AgentModelConfig(
                name="Coder",
                provider="gemini",
                model="gemini-3.8-flash",
                api_key=os.getenv("GEMINI_API_KEY"),
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                temperature=0.0,
                max_tokens=8192,
                timeout=120,
                max_retries=2,
            )
        else:
            # Control: Groq GPT-OSS 120B
            config.coder = AgentModelConfig(
                name="Coder",
                provider="groq",
                model="openai/gpt-oss-120b",
                api_key=os.getenv("GROQ_API_KEY"),
                base_url="https://api.groq.com/openai/v1",
                temperature=0.0,
                max_tokens=4096,
                timeout=120,
                max_retries=2,
            )
    else:
        config.mode = ExecutionMode.MOCK
        config.provider_type = ProviderType.MOCK
        config.coder = AgentModelConfig(
            name="Coder",
            provider="mock",
            model=f"mock-coder-{coder_variant}",
        )

    return config


def main():
    parser = argparse.ArgumentParser(description="Isolated child worker for DDIV Coder Ablation.")
    parser.add_argument("--task-id", type=str, required=True, help="Task / instance ID")
    parser.add_argument("--coder-variant", type=str, required=True, choices=["coder_a", "coder_b"], help="Coder variant: coder_a (GPT-OSS 120b) or coder_b (Gemini 3.8 Flash)")
    parser.add_argument("--condition", type=str, default="full_ddiv", help="Experiment condition (default: full_ddiv)")
    parser.add_argument("--experiment-id", type=str, default="coder_ablation_v21_20261012", help="Experiment ID")
    parser.add_argument("--workspace-root", type=str, required=True, help="Isolated workspace root directory")
    parser.add_argument("--output-file", type=str, required=True, help="Target JSON path for the independent result record")
    parser.add_argument("--log-file", type=str, required=True, help="Target log file for worker stdout/stderr")
    parser.add_argument("--provider", type=str, default="mock", choices=["mock", "real"], help="Model provider mode")
    parser.add_argument("--dataset", type=str, default="data/swebench/test-00000-of-00001.parquet", help="Dataset path")

    args = parser.parse_args()

    # Reconfigure stdout/stderr streams to UTF-8
    for stream in (sys.__stdout__, sys.__stderr__, sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

    log_path = Path(args.log_file).resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    sys.stdout = LoggerWriter(sys.__stdout__, log_path)
    sys.stderr = LoggerWriter(sys.__stderr__, log_path)

    cond = ExperimentCondition.from_str(args.condition)
    config = create_ablation_config(args.coder_variant, args.provider)

    # Isolated adapter injection for Coder B (Gemini)
    if args.coder_variant == "coder_b" and args.provider == "real":
        from models.base import ModelConfig
        from models.registry import ModelRegistry
        from scripts.gemini_coder_adapter import GeminiCoderProvider

        orig_get_provider = ModelRegistry.get_provider_for_agent

        def patched_get_provider(self, agent_config):
            if agent_config.name == "Coder" and agent_config.provider.lower() == "gemini":
                model_cfg = ModelConfig(
                    name=agent_config.name,
                    model_id=agent_config.model,
                    provider=agent_config.provider,
                    api_key=agent_config.api_key,
                    base_url=agent_config.base_url or self.config.api_base_url,
                    temperature=agent_config.temperature,
                    max_tokens=max(agent_config.max_tokens, 8192),
                    timeout=agent_config.timeout,
                    max_retries=agent_config.max_retries,
                )
                provider = GeminiCoderProvider(model_cfg, reasoning_effort="low", min_max_tokens=8192)
                self._providers[agent_config.name] = provider
                return provider
            return orig_get_provider(self, agent_config)

        ModelRegistry.get_provider_for_agent = patched_get_provider

    print("=" * 75)
    print(f" DDIV CODER ABLATION CHILD WORKER [PID: {os.getpid()}]")
    print(f" Experiment ID:   {args.experiment_id}")
    print(f" Task ID:         {args.task_id}")
    print(f" Coder Variant:   {args.coder_variant.upper()} ({config.coder.model} via {config.coder.provider})")
    print(f" Condition:       {cond.value.upper()}")
    print(f" Workspace:       {args.workspace_root}")
    print(f" Provider Mode:   {args.provider.upper()}")
    print(f" Output File:     {args.output_file}")
    print(f" Log File:        {args.log_file}")
    print("=" * 75)
    print()

    try:
        worker = ExperimentWorker(
            task_id=args.task_id,
            condition=cond,
            experiment_id=args.experiment_id,
            workspace_root=args.workspace_root,
            provider=args.provider,
            dataset=args.dataset,
            config=config,
            log_file=args.log_file,
        )

        record = worker.run()

        # Augment record with coder ablation metadata
        rec_data = record.model_dump()
        rec_data["coder_variant"] = args.coder_variant
        rec_data["coder_model"] = config.coder.model
        rec_data["coder_provider"] = config.coder.provider

        out_path = Path(args.output_file).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(rec_data, indent=2), encoding="utf-8")

        print("\n" + "=" * 75)
        print(f" ABLATION WORKER FINISHED: {args.task_id} [{args.coder_variant.upper()}]")
        print(f" Status:          {record.status.value}")
        print(f" Resolved:        {record.resolved}")
        print(f" Attempts:        {record.attempts}")
        print(f" Duration:        {record.execution_duration_seconds:.2f}s")
        print(f" Coder Model:     {config.coder.model}")
        print("=" * 75)
        exit_code = record.worker_exit_code if record.worker_exit_code is not None else 0
        sys.exit(exit_code)

    except Exception as exc:
        err_msg = f"Ablation worker unhandled exception: {exc}\n{traceback.format_exc()}"
        print(f"\n[ERROR] {err_msg}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
