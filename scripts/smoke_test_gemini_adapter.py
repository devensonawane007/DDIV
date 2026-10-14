"""Live Smoke Test for Isolated Gemini Coder Adapter.

Makes exactly ONE request to evaluate structured CoderOutput generation on a simple
non-repository coding task with bounded reasoning effort and expanded token budget.
Never exposes API keys.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
load_dotenv(project_root / ".env", override=True)

from agents.coder import CoderAgent, CoderOutput
from models.base import ModelConfig
from scripts.gemini_coder_adapter import GeminiCoderProvider


def run_live_smoke():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("[ERROR] GEMINI_API_KEY is not set.")
        return {"status": "ERROR", "error": "GEMINI_API_KEY missing"}

    model_id = os.getenv("ABNORMAL_MODEL", "gemini-3.8-flash")
    endpoint = "https://generativelanguage.googleapis.com/v1beta/openai/"

    print("=" * 70)
    print(" GEMINI CODER ADAPTER LIVE SMOKE TEST")
    print(f" Model ID:          {model_id}")
    print(f" Endpoint:          {endpoint}")
    print(f" Max Tokens:        8192")
    print(f" Reasoning Effort:  low")
    print("=" * 70)

    cfg = ModelConfig(
        name="Coder",
        model_id=model_id,
        provider="gemini",
        api_key=api_key,
        base_url=endpoint,
        temperature=0.0,
        max_tokens=8192,
        timeout=120,
        max_retries=1,
    )

    provider = GeminiCoderProvider(cfg, reasoning_effort="low", min_max_tokens=8192)

    prompt = (
        "=== SOURCE CODE IN RELEVANT FILES ===\n"
        "File: src/math_utils.py\n"
        "```python\n"
        "def divide(a: float, b: float) -> float:\n"
        "    \"\"\"Divide a by b.\"\"\"\n"
        "    return a / b\n"
        "```\n\n"
        "=== ISSUE DESCRIPTION ===\n"
        "Calling divide(10, 0) raises an unhandled ZeroDivisionError. "
        "It should check if b == 0 and raise ValueError('division by zero') with a clear message.\n\n"
        "Synthesize the smallest correct code modification resolving the issue.\n"
        "Output JSON with keys: behavioral_analysis, existing_behavior, smallest_change_plan, "
        "regression_risks, modifications, patch, modified_files, reasoning_summary, confidence.\n"
        "Under 'modifications', provide structured edits with: path, target_symbol, operation, anchor, code, reason.\n"
        "The 'anchor' MUST be an exact verbatim substring from the source code provided above."
    )

    coder_agent = CoderAgent(provider)
    system_prompt = coder_agent.build_system_prompt()

    print("[*] Dispatching single live generation request to Gemini...")
    t0 = time.time()
    resp = provider.generate(
        prompt=prompt,
        system_prompt=system_prompt,
        response_schema=CoderOutput,
    )
    latency = time.time() - t0

    result = {
        "timestamp": time.time(),
        "model_id": model_id,
        "endpoint": endpoint,
        "latency_seconds": round(latency, 2),
        "prompt_tokens": resp.prompt_tokens,
        "completion_tokens": resp.completion_tokens,
        "total_tokens": resp.total_tokens,
        "request_id": resp.request_id,
        "error": resp.error,
        "error_category": resp.error_category,
        "raw_text_length": len(resp.raw_text),
        "raw_text_preview": resp.raw_text[:300] if resp.raw_text else "",
        "parsed_json_present": resp.parsed_json is not None,
        "pydantic_validation_success": False,
        "validation_errors": None,
        "modifications_count": 0,
        "modifications_preview": [],
    }

    if resp.error:
        print(f"[!] Request returned error: [{resp.error_category}] {resp.error}")
    else:
        print(f"[+] Request completed successfully in {latency:.2f}s")
        print(f"    Tokens: {resp.total_tokens} (prompt: {resp.prompt_tokens}, completion: {resp.completion_tokens})")

    if resp.parsed_json is not None:
        try:
            val_obj = CoderOutput.model_validate(resp.parsed_json)
            result["pydantic_validation_success"] = True
            result["modifications_count"] = len(val_obj.modifications)
            result["modifications_preview"] = [
                {
                    "path": m.path,
                    "target_symbol": m.target_symbol,
                    "operation": m.operation,
                    "anchor": m.anchor,
                    "reason": m.reason,
                }
                for m in val_obj.modifications
            ]
            print(f"[+] Pydantic Validation SUCCESS: CoderOutput conforms perfectly to schema.")
            print(f"    Modifications count: {len(val_obj.modifications)}")
            for i, m in enumerate(val_obj.modifications, 1):
                print(f"    Mod {i}: {m.operation} on '{m.path}' (anchor: {repr(m.anchor[:40])})")
        except Exception as val_err:
            result["validation_errors"] = str(val_err)
            print(f"[-] Pydantic Validation FAILED: {val_err}")

    # Write output to gemini_smoke_result.json
    out_file = project_root / "gemini_smoke_result.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(f"[*] Smoke result written to {out_file}")

    return result


if __name__ == "__main__":
    run_live_smoke()
