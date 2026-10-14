"""Pre-launch gate check script for DDIV v2.1 benchmark execution."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

import os
import requests

EXPECTED_CHECKPOINT_HASH = "3088b7c08707b30b6b87064844c45595520a4c86c599e9b1fcb45af3b3d4e52e"
EXPECTED_MANIFEST_HASH = "16fb9c829a2163f8187e3ffaec9cde585a843af905459a4e6467995792e2a605"
FROZEN_DIRS = ["agents", "recovery", "evaluation", "memory", "models"]

BATCH_TASKS = {
    1: ["pylint-dev__pylint-6903", "mwaskom__seaborn-3187", "pydata__xarray-7393"],
    2: ["astropy__astropy-8872", "astropy__astropy-14508", "psf__requests-2931"],
    3: ["pytest-dev__pytest-8399", "sympy__sympy-23413", "matplotlib__matplotlib-26342"],
    4: ["scikit-learn__scikit-learn-26323", "pydata__xarray-4966", "pylint-dev__pylint-4970"],
    5: ["sympy__sympy-13878", "django__django-16429", "sphinx-doc__sphinx-8638"],
    6: ["django__django-11141", "pytest-dev__pytest-7982", "scikit-learn__scikit-learn-13496"],
    7: ["sphinx-doc__sphinx-8269", "matplotlib__matplotlib-20676"],
}

# Empirical estimates (+30% safety margin)
ESTIMATED_TOKENS_PER_BATCH = {
    1: {"gpt_oss_120b": 161522, "qwen_27b": 114321},
    2: {"gpt_oss_120b": 161522, "qwen_27b": 114321},
    3: {"gpt_oss_120b": 161522, "qwen_27b": 114321},
    4: {"gpt_oss_120b": 161522, "qwen_27b": 114321},
    5: {"gpt_oss_120b": 161522, "qwen_27b": 114321},
    6: {"gpt_oss_120b": 161522, "qwen_27b": 114321},
    7: {"gpt_oss_120b": 107682, "qwen_27b": 76214},
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def check_gate(
    batch_num: int,
    verified_gpt_available: Optional[int] = None,
    verified_qwen_available: Optional[int] = None,
    require_gpt_quota: Optional[bool] = None,
    check_ollama: bool = True,
) -> bool:
    print("=" * 70)
    print(f" DDIV v2.2 PRE-LAUNCH GATE CHECK: BATCH {batch_num}")
    print("=" * 70)
    passed = True

    # 1. Checkpoint Hash
    chk_path = Path("data/experiments/benchmark_v2_1/checkpoint.json")
    if not chk_path.exists():
        print(f"[-] Checkpoint missing: {chk_path}")
        passed = False
    else:
        chk_hash = sha256_file(chk_path)
        if chk_hash == EXPECTED_CHECKPOINT_HASH:
            print(f"[+] Checkpoint SHA-256 verified: {chk_hash[:16]}...")
        else:
            print(f"[-] Checkpoint hash MISMATCH: {chk_hash} != {EXPECTED_CHECKPOINT_HASH}")
            passed = False

    # 2. Manifest Hash
    mnf_path = Path("data/experiments/benchmark_v2_tasks.json")
    if not mnf_path.exists():
        print(f"[-] Task manifest missing: {mnf_path}")
        passed = False
    else:
        mnf_hash = sha256_file(mnf_path)
        if mnf_hash == EXPECTED_MANIFEST_HASH:
            print(f"[+] Task Manifest SHA-256 verified: {mnf_hash[:16]}...")
        else:
            print(f"[-] Task manifest hash MISMATCH: {mnf_hash} != {EXPECTED_MANIFEST_HASH}")
            passed = False

    # 3. Frozen Dirs Status
    proc = subprocess.run(["git", "status", "--porcelain"] + FROZEN_DIRS, capture_output=True, text=True)
    if proc.stdout.strip():
        print(f"[-] Frozen directories MODIFIED:\n{proc.stdout}")
        passed = False
    else:
        print("[+] Frozen codebase directories clean (agents/, recovery/, evaluation/, memory/, models/)")

    # 4. Windows Longpaths
    proc_lp = subprocess.run(["git", "config", "--global", "core.longpaths"], capture_output=True, text=True)
    if proc_lp.stdout.strip().lower() == "true":
        print("[+] Windows git core.longpaths enabled (true)")
    else:
        print("[-] Windows git core.longpaths NOT enabled! Run: git config --global core.longpaths true")
        passed = False

    # 5. Dataset File
    ds_path = Path("data/swebench/test-00000-of-00001.parquet")
    if ds_path.exists() and ds_path.stat().st_size > 1_000_000:
        print(f"[+] SWE-bench Verified parquet dataset confirmed ({ds_path.stat().st_size:,} bytes)")
    else:
        print(f"[-] SWE-bench dataset missing or corrupted at {ds_path}")
        passed = False

    # 6. Task Assignment Verification
    tasks = BATCH_TASKS.get(batch_num, [])
    print(f"\n[+] Batch {batch_num} Tasks ({len(tasks)} tasks):")
    for t in tasks:
        print(f"    - {t}")

    # 7. Local Ollama Readiness & Zero Fallback
    if check_ollama:
        ollama_base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        coder_model = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
        try:
            tags_res = requests.get(f"{ollama_base}/api/tags", timeout=5)
            if tags_res.status_code == 200:
                models_list = [m.get("name", "") for m in tags_res.json().get("models", [])]
                if any(coder_model in m for m in models_list):
                    print(f"[+] Local Ollama ready at {ollama_base} with model '{coder_model}' confirmed present")
                else:
                    print(f"[-] Local Ollama model '{coder_model}' NOT found at {ollama_base}. Present: {models_list}")
                    passed = False
            else:
                print(f"[-] Local Ollama server error at {ollama_base}: status {tags_res.status_code}")
                passed = False
        except Exception as exc:
            print(f"[-] Cannot connect to local Ollama server at {ollama_base}: {exc}")
            passed = False

        # Verify zero fallback configuration
        coder_prov = os.getenv("DDIV_CODER_PROVIDER", "ollama").lower()
        if coder_prov == "ollama":
            print("[+] Coder provider configured as 'ollama' with zero cloud fallback enabled")
        else:
            print(f"[-] Coder provider is '{coder_prov}', expected 'ollama' for quota-free evaluation")
            passed = False

    # 8. Quota Demand vs. Verified Capacity
    est = ESTIMATED_TOKENS_PER_BATCH.get(batch_num, {})
    needed_gpt = est.get("gpt_oss_120b", 161522)
    needed_qwen = est.get("qwen_27b", 114321)

    print(f"\n[*] Projected Token Demand for Batch {batch_num} (with +30% safety buffer):")
    print(f"    - Coder (qwen2.5-coder:7b via Ollama): Quota-free local inference")
    print(f"    - Supporting Agents (qwen/qwen3.8-27b via Groq): ~{needed_qwen:,} tokens")

    print("\n[*] Provider Quota Verification (Requires Confirmation via Groq Console Dashboard):")
    print("    [!] NOTE: Groq HTTP headers only expose TPM/RPM (per-minute), not daily TPD.")
    print("    [!] The claimed available quota is an operator-reported safety allocation,")
    print("    [!] and cannot be queried or validated independently via API headers.")
    print("    [!] Any quota exhaustion during execution halts the run and remains strictly")
    print("    [!] isolated from software repair outcomes.")

    # Determine if GPT quota is required (default True for backward compatibility with dual-model test, unless explicitly False)
    check_gpt = require_gpt_quota if require_gpt_quota is not None else True

    if check_gpt:
        if verified_gpt_available is None or verified_gpt_available <= 0:
            print("    [-] openai/gpt-oss-120b (Legacy Coder): UNVERIFIED. Dashboard confirmation required.")
            passed = False
        elif verified_gpt_available < needed_gpt:
            deficit = needed_gpt - verified_gpt_available
            print(f"    [-] openai/gpt-oss-120b: Available quota ({verified_gpt_available:,}) is LESS than needed ({needed_gpt:,}, deficit: {deficit:,}).")
            passed = False
        else:
            buffer = verified_gpt_available - needed_gpt
            print(f"    [+] openai/gpt-oss-120b: Verified capacity ({verified_gpt_available:,}) meets demand ({needed_gpt:,}, buffer: +{buffer:,}).")

    # Validate Qwen 3.8 27B capacity for supporting agents
    if verified_qwen_available is None or verified_qwen_available <= 0:
        print("    [-] qwen/qwen3.8-27b (Supporting Agents): UNVERIFIED (Missing, zero, or negative input). Dashboard confirmation required.")
        passed = False
    elif verified_qwen_available < needed_qwen:
        deficit = needed_qwen - verified_qwen_available
        print(f"    [-] qwen/qwen3.8-27b: Claimed quota ({verified_qwen_available:,}) is LESS than needed ({needed_qwen:,}, deficit: {deficit:,}).")
        passed = False
    else:
        buffer = verified_qwen_available - needed_qwen
        print(f"    [+] qwen/qwen3.8-27b: Claimed capacity ({verified_qwen_available:,}) meets demand ({needed_qwen:,}, buffer: +{buffer:,}).")

    if not passed:
        print("\n    [-] GATE RESULT: NO-GO (One or more safety requirements, Ollama readiness, or quota thresholds unmet/unverified).")
    else:
        print("\n    [+] GATE RESULT: GO (All safety checks, local Ollama Coder readiness, and supporting-agent quota thresholds satisfied).")

    print("=" * 70)
    decision = "GO" if passed else "NO-GO"
    print(f" FINAL GATE DECISION: {decision}")
    print("=" * 70)
    return passed


def main():
    parser = argparse.ArgumentParser(description="Pre-launch gate check for DDIV v2.2 benchmark batches.")
    parser.add_argument("--batch", type=int, required=True, choices=range(1, 8), help="Batch number (1-7)")
    parser.add_argument(
        "--verified-groq-available",
        "--verified-qwen-available",
        dest="verified_groq_available",
        type=int,
        default=None,
        help="Manually verified available tokens for qwen/qwen3.8-27b supporting agents from Groq dashboard",
    )
    parser.add_argument(
        "--verified-gpt-available",
        type=int,
        default=None,
        help="Legacy: verified available tokens for openai/gpt-oss-120b",
    )
    parser.add_argument(
        "--verified-tpd-available",
        type=int,
        default=None,
        help="Convenience alias to set supporting agent available quota",
    )
    parser.add_argument(
        "--no-check-ollama",
        dest="check_ollama",
        action="store_false",
        default=True,
        help="Skip local Ollama connectivity check",
    )
    args = parser.parse_args()

    qwen_avail = args.verified_groq_available if args.verified_groq_available is not None else args.verified_tpd_available
    gpt_avail = args.verified_gpt_available

    success = check_gate(
        args.batch,
        verified_gpt_available=gpt_avail,
        verified_qwen_available=qwen_avail,
        require_gpt_quota=(gpt_avail is not None),
        check_ollama=args.check_ollama,
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
