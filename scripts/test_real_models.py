"""Real model smoke test script for DDIV.

Executes a single invocation for each agent's configured real model.
Verifies connectivity, authentication, model existence, response return,
and conversion to ProviderResponse without running benchmarks or pipelines.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Optional

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

from core.config import AgentModelConfig, DDIVConfig, ExecutionMode, ProviderType
from models.base import ModelConfig, ProviderResponse
from models.registry import ModelRegistry
from models.providers import (
    ErrorCategory,
    sanitize_error_message,
)


def run_smoke_test_for_agent(name: str, agent_cfg: AgentModelConfig, registry: ModelRegistry) -> dict:
    """Run a single isolated smoke test for one agent model."""
    provider_name = agent_cfg.provider
    model_id = agent_cfg.model
    api_key = agent_cfg.api_key

    # Check for placeholder / unconfigured
    if not model_id or model_id.startswith("REPLACE_") or "<" in model_id:
        return {
            "provider": provider_name,
            "model_id": model_id or "not_configured",
            "success": False,
            "latency": 0.0,
            "error_category": ErrorCategory.CONFIGURATION_ERROR.value,
            "detail": f"Model ID is not configured (found '{model_id}'). Set in .env.",
        }

    if not api_key:
        return {
            "provider": provider_name,
            "model_id": model_id,
            "success": False,
            "latency": 0.0,
            "error_category": ErrorCategory.CONFIGURATION_ERROR.value,
            "detail": "API key or token is not configured in .env.",
        }

    try:
        provider = registry.get_provider_for_agent(agent_cfg)
        test_prompt = "Return exactly the word OK."
        start_t = time.time()
        resp: ProviderResponse = provider.generate(
            prompt=test_prompt,
            system_prompt="You are a helpful software engineering assistant.",
        )
        latency = resp.latency_seconds or (time.time() - start_t)

        if resp.error:
            sanitized = sanitize_error_message(resp.error, api_key)
            return {
                "provider": provider_name,
                "model_id": model_id,
                "success": False,
                "latency": latency,
                "error_category": resp.error_category or ErrorCategory.PROVIDER_UNAVAILABLE.value,
                "detail": sanitized,
            }

        return {
            "provider": provider_name,
            "model_id": model_id,
            "success": True,
            "latency": latency,
            "request_id": resp.request_id,
            "error_category": None,
            "detail": resp.raw_text.strip()[:60],
        }

    except Exception as e:
        sanitized = sanitize_error_message(str(e), api_key)
        return {
            "provider": provider_name,
            "model_id": model_id,
            "success": False,
            "latency": 0.0,
            "request_id": None,
            "error_category": ErrorCategory.PROVIDER_UNAVAILABLE.value,
            "detail": sanitized,
        }


def main():
    print("=" * 70)
    print(" DDIV Real Model Smoke Test")
    print("=" * 70)
    print()

    config = DDIVConfig.load_from_env()
    # Force real provider resolution in registry
    config.mode = ExecutionMode.REAL
    config.provider_type = ProviderType.OPENAI_COMPATIBLE
    registry = ModelRegistry(config)

    agents = [
        ("Locator", config.locator),
        ("Coder", config.coder),
        ("Tester", config.tester),
        ("Supervisor", config.supervisor),
    ]

    all_passed = True

    for name, agent_cfg in agents:
        res = run_smoke_test_for_agent(name, agent_cfg, registry)
        status_str = "SUCCESS" if res["success"] else "FAILURE"
        if not res["success"]:
            all_passed = False

        print(f"Role:           {name}")
        print(f"Provider:       {res['provider']}")
        print(f"Model ID:       {res['model_id']}")
        print(f"Status:         {status_str}")
        print(f"Latency:        {res['latency']:.2f}s")
        if res.get("request_id"):
            print(f"Request ID:     {res['request_id']}")
        if res["error_category"]:
            print(f"Error Category: {res['error_category']}")
            print(f"Detail:         {res['detail']}")
        else:
            print(f"Response:       {res['detail']}")
        print("-" * 50)

    print()
    if all_passed:
        print("Overall Smoke Test: ALL PASSED")
        sys.exit(0)
    else:
        print("Overall Smoke Test: SOME FAILED OR UNCONFIGURED")
        sys.exit(1)


if __name__ == "__main__":
    main()
