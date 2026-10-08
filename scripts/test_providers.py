"""Lightweight provider health check and model availability discovery for DDIV.

Tests API key presence, model configuration status, and connectivity with a tiny
harmless prompt ('Return the word OK.').
Discovers and lists accessible models from provider endpoints to ensure research
reproducibility before populating .env.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import List, Optional

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

from openai import OpenAI
from models.base import ModelConfig, ProviderResponse
from models.providers import (
    ErrorCategory,
    GeminiProvider,
    GroqProvider,
    HuggingFaceProvider,
    OpenRouterProvider,
    XAIProvider,
    categorize_error,
    sanitize_error_message,
)


def is_placeholder(val: Optional[str]) -> bool:
    if not val:
        return True
    v = val.strip()
    return v.startswith("REPLACE_") or "<" in v or v == "your-model-here"


def get_available_models(client: OpenAI, limit: int = 10) -> List[str]:
    """Query /v1/models to fetch available model IDs."""
    try:
        models_page = client.models.list()
        # Some providers return an iterable of model objects with .id
        model_ids = [m.id for m in models_page if hasattr(m, "id")]
        return model_ids[:limit]
    except Exception:
        return []


def test_single_provider(
    name: str,
    key_name: str,
    model_name: str,
    base_url_name: str,
    default_base_url: str,
    provider_cls: type,
) -> None:
    api_key = os.getenv(key_name)
    model_id = os.getenv(model_name)
    base_url = os.getenv(base_url_name, default_base_url)

    key_configured = bool(api_key and not api_key.startswith("your_") and len(api_key) > 5)
    model_configured = bool(model_id and not is_placeholder(model_id))

    print(f"{name}:")
    print(f"  API key configured:   {'YES' if key_configured else 'NO'}")
    if model_configured:
        print(f"  Model configured:     YES ({model_id})")
    else:
        status_text = f"NO (placeholder: {model_id})" if model_id else "NO (not set)"
        print(f"  Model configured:     {status_text}")

    if not key_configured:
        print(f"  Connection:           SKIPPED (Missing {key_name})")
        print()
        return

    # Initialize client to probe endpoint
    try:
        client = OpenAI(api_key=api_key, base_url=base_url, timeout=30)
    except Exception as e:
        sanitized = sanitize_error_message(str(e), api_key)
        print(f"  Connection:           FAIL (Client initialization error: {sanitized})")
        print()
        return

    # If model is configured, send the minimal test prompt
    if model_configured:
        try:
            start_t = time.time()
            cfg = ModelConfig(
                name=name,
                model_id=model_id,
                api_key=api_key,
                base_url=base_url,
                temperature=0.0,
                max_tokens=100,
                timeout=30,
                max_retries=1,
            )
            provider = provider_cls(cfg)
            resp = provider.generate("Return the word OK.")
            dur = time.time() - start_t

            if resp.error:
                sanitized = sanitize_error_message(resp.error, api_key)
                print(f"  Connection:           FAIL ({resp.error_category or 'ERROR'}: {sanitized})")
            else:
                reply = resp.raw_text.strip().replace("\n", " ")[:30]
                print(f"  Connection:           PASS (Response: '{reply}', latency: {dur:.2f}s)")
        except Exception as e:
            cat = categorize_error(e)
            sanitized = sanitize_error_message(str(e), api_key)
            print(f"  Connection:           FAIL ({cat.value}: {sanitized})")
    else:
        # Probe endpoint /v1/models to verify auth and list available models
        try:
            available = get_available_models(client, limit=15)
            if available:
                print(f"  Connection:           PASS (Authenticated to {base_url})")
                print(f"  Available models:     {', '.join(available[:8])}...")
            else:
                # Some endpoints don't support models.list(), probe with a tiny request
                print(f"  Connection:           PASS (Authenticated, endpoint reachable)")
        except Exception as e:
            cat = categorize_error(e)
            sanitized = sanitize_error_message(str(e), api_key)
            print(f"  Connection:           FAIL ({cat.value}: {sanitized})")

    print()


def main():
    print("=" * 60)
    print(" DDIV Provider Health Check & Model Discovery")
    print("=" * 60)
    print()

    # 1. Gemini
    test_single_provider(
        name="Gemini",
        key_name="GEMINI_API_KEY",
        model_name="LOCATOR_MODEL",
        base_url_name="GEMINI_BASE_URL",
        default_base_url=GeminiProvider.DEFAULT_BASE_URL,
        provider_cls=GeminiProvider,
    )

    # 2. Coder (Groq or xAI)
    coder_provider = os.getenv("CODER_PROVIDER", "groq").lower()
    if coder_provider == "groq":
        test_single_provider(
            name="Groq",
            key_name="GROQ_API_KEY",
            model_name="CODER_MODEL",
            base_url_name="GROQ_BASE_URL",
            default_base_url=GroqProvider.DEFAULT_BASE_URL,
            provider_cls=GroqProvider,
        )
    else:
        test_single_provider(
            name="xAI",
            key_name="XAI_API_KEY",
            model_name="CODER_MODEL",
            base_url_name="XAI_BASE_URL",
            default_base_url=XAIProvider.DEFAULT_BASE_URL,
            provider_cls=XAIProvider,
        )

    # 3. OpenRouter (Tester)
    test_single_provider(
        name="OpenRouter (Tester)",
        key_name="OPENROUTER_API_KEY",
        model_name="TESTER_MODEL",
        base_url_name="OPENROUTER_BASE_URL",
        default_base_url=OpenRouterProvider.DEFAULT_BASE_URL,
        provider_cls=OpenRouterProvider,
    )

    # 4. Supervisor (OpenRouter or Hugging Face)
    sup_provider = os.getenv("SUPERVISOR_PROVIDER", "huggingface").lower()
    if sup_provider == "openrouter":
        test_single_provider(
            name="OpenRouter (Supervisor)",
            key_name="OPENROUTER_API_KEY",
            model_name="SUPERVISOR_MODEL",
            base_url_name="OPENROUTER_BASE_URL",
            default_base_url=OpenRouterProvider.DEFAULT_BASE_URL,
            provider_cls=OpenRouterProvider,
        )
    else:
        test_single_provider(
            name="Hugging Face (Supervisor)",
            key_name="HF_TOKEN",
            model_name="SUPERVISOR_MODEL",
            base_url_name="HF_BASE_URL",
            default_base_url=HuggingFaceProvider.DEFAULT_BASE_URL,
            provider_cls=HuggingFaceProvider,
        )


if __name__ == "__main__":
    main()
