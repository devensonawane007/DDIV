"""Live smoke test for Ollama CoderAgent integration.

Tests real end-to-end execution of CoderAgent backed by local Ollama (qwen2.5-coder:7b)
inside an isolated disposable workspace, verifying:
1. Live connectivity to http://localhost:11434
2. Schema-validated CoderOutput generation
3. Exact prompt/eval token counting and latency
4. Patch construction with DemoPatchBuilder
5. Live patch application and functional test verification
6. Output recorded to results/local_ollama_coder/smoke_test_result.json
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

# Ensure project root is in sys.path
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Set Ollama provider environment variables
os.environ["DDIV_CODER_PROVIDER"] = "ollama"
os.environ["OLLAMA_BASE_URL"] = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
os.environ["OLLAMA_MODEL"] = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
os.environ["OLLAMA_TIMEOUT_SECONDS"] = os.getenv("OLLAMA_TIMEOUT_SECONDS", "240")
os.environ["DDIV_MODE"] = "real"
os.environ["PROVIDER_TYPE"] = "openai_compatible"

from agents.base import AgentInputMetadata
from agents.coder import CoderAgent, CoderOutput
from core.config import DDIVConfig
from models.registry import ModelRegistry
from scripts.demo_patch_builder import DemoPatchBuilder
from scripts.ollama_coder_adapter import OllamaProvider


def run_live_smoke_test() -> Dict[str, Any]:
    print("=" * 75)
    print(" DDIV LIVE SMOKE TEST: LOCAL OLLAMA CODER AGENT")
    print(f" Provider:   {os.environ['DDIV_CODER_PROVIDER']}")
    print(f" Base URL:   {os.environ['OLLAMA_BASE_URL']}")
    print(f" Model:      {os.environ['OLLAMA_MODEL']}")
    print(f" Timeout:    {os.environ['OLLAMA_TIMEOUT_SECONDS']}s")
    print("=" * 75)

    # 1. Setup disposable workspace
    ws_dir = Path("data/workspaces/smoke_test_ollama").resolve()
    if ws_dir.exists():
        shutil.rmtree(ws_dir, ignore_errors=True)
    ws_dir.mkdir(parents=True, exist_ok=True)

    target_file = ws_dir / "calculator.py"
    initial_code = (
        "def add(a: int, b: int) -> int:\n"
        "    # Bug: subtracts instead of adds\n"
        "    return a - b\n"
    )
    target_file.write_text(initial_code, encoding="utf-8")
    print(f"[+] Created disposable test workspace at: {ws_dir}")
    print(f"[+] Initial target code in calculator.py:\n{initial_code.strip()}\n")

    # 2. Initialize Config & Provider
    config = DDIVConfig.load_from_env()
    assert config.coder.provider == "ollama", f"Expected provider 'ollama', got {config.coder.provider}"
    assert config.coder.model == "qwen2.5-coder:7b", f"Expected model 'qwen2.5-coder:7b', got {config.coder.model}"

    registry = ModelRegistry(config)
    provider = registry.get_provider_for_agent(config.coder)
    assert isinstance(provider, OllamaProvider), f"Expected OllamaProvider, got {type(provider)}"
    print(f"[+] Successfully instantiated {type(provider).__name__}")

    # 3. Instantiate CoderAgent
    coder = CoderAgent(provider)

    prompt_context = {
        "issue": (
            "In calculator.py, function `add(a, b)` computes `a - b` instead of `a + b`. "
            "Fix it so that `add(a, b)` returns `a + b`."
        ),
        "source_files": f"=== calculator.py ===\n{initial_code}",
        "locator_result": {
            "relevant_files": ["calculator.py"],
            "relevant_symbols": ["add"],
        },
    }
    metadata = AgentInputMetadata(task_id="smoke-test-calc", run_id="smoke-run-001", attempt=1)

    print("[*] Invoking CoderAgent.execute() via Ollama (qwen2.5-coder:7b)...")
    start_time = time.time()
    result = coder.execute(prompt_context, metadata)
    elapsed = time.time() - start_time
    print(f"[*] Response received in {elapsed:.2f}s")

    smoke_record: Dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "provider": config.coder.provider,
        "model_id": config.coder.model,
        "base_url": config.coder.base_url,
        "success": result.success,
        "error": result.error,
        "error_code": result.error_code,
        "latency_seconds": result.latency_seconds,
        "prompt_tokens": result.prompt_tokens,
        "completion_tokens": result.completion_tokens,
        "total_tokens": result.total_tokens,
        "raw_response": result.raw_response,
        "coder_output": result.output.model_dump() if result.output else None,
        "patch_applied": False,
        "functional_verification": False,
    }

    if not result.success or not result.output:
        print(f"[-] CoderAgent execution FAILED!")
        print(f"    Error Code: {result.error_code}")
        print(f"    Error Msg:  {result.error}")
        print(f"    Raw Response:\n{result.raw_response[:500]}")
        _save_and_exit(smoke_record, False)
        return smoke_record

    print("[+] CoderAgent execution SUCCEEDED!")
    print(f"    Confidence:        {result.output.confidence}")
    print(f"    Modifications:     {len(result.output.modifications)}")
    print(f"    Prompt Tokens:     {result.prompt_tokens}")
    print(f"    Completion Tokens: {result.completion_tokens}")
    print(f"    Total Tokens:      {result.total_tokens}")
    print(f"    Latency:           {result.latency_seconds:.2f}s")

    for i, mod in enumerate(result.output.modifications, 1):
        print(f"    Modification #{i}: path='{mod.path}', op='{mod.operation}', anchor='{mod.anchor.strip()}'")

    # 4. Patch Construction using DemoPatchBuilder
    print("\n[*] Constructing unified diff using DemoPatchBuilder...")
    builder = DemoPatchBuilder()
    patch_result = builder.build_patch(result.output.modifications, base_dir=ws_dir)

    smoke_record["patch_builder_success"] = patch_result.success
    smoke_record["patch_builder_error"] = patch_result.error_message
    smoke_record["patch_builder_category"] = patch_result.error_category
    smoke_record["unified_diff"] = patch_result.unified_diff

    if not patch_result.success:
        print(f"[-] Patch construction FAILED: {patch_result.error_message} [{patch_result.error_category}]")
        _save_and_exit(smoke_record, False)
        return smoke_record

    print("[+] Unified diff built successfully:")
    print("---" * 20)
    print(patch_result.unified_diff)
    print("---" * 20)

    # 5. Apply Patch and Verify Functionality
    print("\n[*] Applying patch in disposable workspace...")
    patch_file = ws_dir / "fix.patch"
    patch_file.write_text(patch_result.unified_diff, encoding="utf-8")

    import subprocess
    apply_res = subprocess.run(
        ["git", "apply", str(patch_file)],
        cwd=ws_dir,
        capture_output=True,
        text=True,
    )
    if apply_res.returncode != 0:
        # Fallback to direct file application if not a git repository
        print(f"[!] git apply returned code {apply_res.returncode} (workspace is not a git repo). Using patch manager...")
        from evaluation.patch_manager import PatchManager
        pm = PatchManager()
        pm_res = pm.apply_patch(ws_dir, patch_result.unified_diff)
        if not pm_res.applied:
            print(f"[-] Patch application failed: {pm_res.error_message}")
            smoke_record["patch_applied"] = False
            _save_and_exit(smoke_record, False)
            return smoke_record

    smoke_record["patch_applied"] = True
    print("[+] Patch applied successfully to calculator.py!")

    updated_code = target_file.read_text(encoding="utf-8")
    print(f"[+] Updated code in calculator.py:\n{updated_code.strip()}\n")

    # 6. Functional Verification
    sys.path.insert(0, str(ws_dir))
    try:
        import importlib
        if "calculator" in sys.modules:
            del sys.modules["calculator"]
        import calculator
        importlib.reload(calculator)
        add_result = calculator.add(2, 3)
        assert add_result == 5, f"calculator.add(2, 3) returned {add_result}, expected 5"
        print(f"[+] Functional verification PASSED: calculator.add(2, 3) == {add_result}")
        smoke_record["functional_verification"] = True
    except Exception as exc:
        print(f"[-] Functional verification FAILED: {exc}")
        smoke_record["functional_verification"] = False
        _save_and_exit(smoke_record, False)
        return smoke_record

    _save_and_exit(smoke_record, True)
    return smoke_record


def _save_and_exit(record: Dict[str, Any], passed: bool):
    out_dir = Path("results/local_ollama_coder").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "smoke_test_result.json"
    out_file.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(f"\n[+] Smoke test audit record written to: {out_file}")
    print("=" * 75)
    if passed:
        print(" LIVE SMOKE TEST RESULT: PASSED")
    else:
        print(" LIVE SMOKE TEST RESULT: FAILED")
    print("=" * 75)


if __name__ == "__main__":
    run_live_smoke_test()
