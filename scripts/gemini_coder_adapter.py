"""Isolated Gemini Coder Provider Adapter for DDIV Coder Model Ablation.

Provides structured CoderOutput generation using Google Gemini via the
OpenAI-compatible endpoint with bounded reasoning effort, expanded token
headroom, robust JSON extraction, truncation detection, and credential sanitization.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Type
from pydantic import BaseModel

from models.base import ModelConfig, ModelProvider, ProviderResponse
from models.providers import (
    ErrorCategory,
    categorize_error,
    is_retryable_error,
    sanitize_error_message,
)


def robust_extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Robustly extract and parse a JSON dictionary from LLM output.
    
    Handles:
    - Pure JSON
    - Markdown code-fenced JSON (```json ... ``` or ``` ... ```)
    - Surrounding conversational prose / whitespace
    - Unescaped control characters (strict=False)
    - Trailing commas in objects or lists
    """
    if not text:
        return None
    
    cleaned = text.strip()

    # 1. Direct JSON parse
    try:
        data = json.loads(cleaned, strict=False)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # 2. Markdown fence extraction (first matching fenced block)
    fence_pattern = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)
    for match in fence_pattern.finditer(cleaned):
        block = match.group(1).strip()
        try:
            data = json.loads(block, strict=False)
            if isinstance(data, dict):
                return data
        except Exception:
            # Try cleaning trailing commas inside block
            cleaned_block = re.sub(r",\s*([\]}])", r"\1", block)
            try:
                data = json.loads(cleaned_block, strict=False)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass

    # 3. Outer brace heuristic
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        snippet = cleaned[start : end + 1]
        try:
            data = json.loads(snippet, strict=False)
            if isinstance(data, dict):
                return data
        except Exception:
            # Trailing comma cleanup
            cleaned_snippet = re.sub(r",\s*([\]}])", r"\1", snippet)
            try:
                data = json.loads(cleaned_snippet, strict=False)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass

    return None


class GeminiCoderProvider(ModelProvider):
    """Isolated provider adapter for Google Gemini acting as Coder Agent.
    
    Enhancements over default OpenAICompatibleProvider:
    1. Bounded Reasoning Effort: Passes reasoning_effort='low' to avoid token starvation.
    2. Token Headroom: Enforces max_tokens >= 8192 for thinking + full code generation.
    3. Structured Outputs: Attempts native json_schema response_format before json_object.
    4. Truncation Awareness: Explicitly inspects finish_reason == 'length'.
    5. Robust Parsing: Multi-tier fallback extraction with strict=False.
    6. Credential Protection: Scrubs API keys from all error reporting.
    """

    DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

    def __init__(
        self,
        config: ModelConfig,
        reasoning_effort: str = "low",
        min_max_tokens: int = 8192,
    ):
        super().__init__(config)
        self.provider_name = "gemini"
        self.base_url = config.base_url or self.DEFAULT_BASE_URL
        self.reasoning_effort = reasoning_effort
        # Ensure sufficient token headroom for reasoning + CoderOutput JSON
        self.max_tokens = max(config.max_tokens, min_max_tokens)
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
                api_key = self.config.api_key or os.getenv("GEMINI_API_KEY") or "EMPTY"
                self._client = OpenAI(
                    api_key=api_key,
                    base_url=self.base_url,
                    timeout=self.config.timeout,
                )
            except ImportError:
                raise RuntimeError("openai package is required for GeminiCoderProvider")
        return self._client

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        response_schema: Optional[Type[BaseModel]] = None,
    ) -> ProviderResponse:
        if not self.config.model_id:
            return ProviderResponse(
                raw_text="",
                model_id="unconfigured",
                provider=self.provider_name,
                error="Model ID is not configured.",
                error_category=ErrorCategory.CONFIGURATION_ERROR.value,
            )

        client = self._get_client()
        messages: List[Dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # Append schema instructions as prompt guidance
        if response_schema:
            schema_json = json.dumps(response_schema.model_json_schema(), indent=2)
            messages[-1]["content"] += (
                f"\n\nCRITICAL: Respond ONLY with a valid JSON object matching this schema:\n"
                f"{schema_json}\n"
                f"Do not include any preamble, conversational commentary, or markdown text outside the JSON."
            )

        start_time = time.time()
        retries = 0
        last_error = ""
        last_category: Optional[ErrorCategory] = None
        max_retries = max(0, self.config.max_retries)

        # Base kwargs
        kwargs: Dict[str, Any] = {
            "model": self.config.model_id,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.max_tokens,
        }

        # Bounded reasoning effort for thinking models
        if self.reasoning_effort:
            kwargs["reasoning_effort"] = self.reasoning_effort

        # Structured outputs configuration
        use_structured_schema = False
        if response_schema:
            try:
                kwargs["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": response_schema.__name__,
                        "schema": response_schema.model_json_schema(),
                    },
                }
                use_structured_schema = True
            except Exception:
                kwargs["response_format"] = {"type": "json_object"}

        while retries <= max_retries:
            try:
                try:
                    response = client.chat.completions.create(**kwargs)
                except Exception as call_err:
                    # If json_schema mode failed, fall back to json_object once
                    if use_structured_schema and "response_format" in str(call_err).lower():
                        kwargs["response_format"] = {"type": "json_object"}
                        use_structured_schema = False
                        response = client.chat.completions.create(**kwargs)
                    # If reasoning_effort is unsupported by endpoint/model, remove it once
                    elif "reasoning_effort" in kwargs and "reasoning_effort" in str(call_err).lower():
                        kwargs.pop("reasoning_effort", None)
                        response = client.chat.completions.create(**kwargs)
                    else:
                        raise call_err

                latency = time.time() - start_time
                choice = response.choices[0] if response.choices else None
                content = (choice.message.content or "").strip() if choice and choice.message else ""
                finish_reason = getattr(choice, "finish_reason", None) if choice else None
                request_id = getattr(response, "id", None)

                tokens = getattr(response, "usage", None)
                prompt_tokens = getattr(tokens, "prompt_tokens", 0) or 0
                completion_tokens = getattr(tokens, "completion_tokens", 0) or 0
                total_tokens = getattr(tokens, "total_tokens", 0) or 0

                error_msg = None
                error_cat = None
                parsed = None

                # Detect token truncation
                if finish_reason == "length":
                    error_msg = (
                        f"TRUNCATED_RESPONSE: Model output hit token limit (max_tokens={self.max_tokens}). "
                        f"Generated text was truncated before completion."
                    )
                    error_cat = ErrorCategory.INVALID_RESPONSE.value
                elif not content:
                    error_msg = "Model returned empty response."
                    error_cat = ErrorCategory.INVALID_RESPONSE.value
                elif response_schema:
                    parsed = robust_extract_json(content)
                    if parsed is None:
                        # Check if raw text looks cut off
                        if content.endswith(("...", '"', ",", "{", "[", "\\")):
                            error_msg = f"TRUNCATED_RESPONSE: Incomplete JSON detected: {content[-100:]}"
                        else:
                            error_msg = f"Failed to extract valid JSON matching schema from output: {content[:200]}"
                        error_cat = ErrorCategory.INVALID_RESPONSE.value

                return ProviderResponse(
                    raw_text=content,
                    parsed_json=parsed,
                    model_id=self.config.model_id,
                    provider=self.provider_name,
                    latency_seconds=latency,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    request_id=request_id,
                    error=error_msg,
                    error_category=error_cat,
                )

            except Exception as e:
                status_code = getattr(e, "status_code", None)
                category = categorize_error(e, status_code)
                last_category = category
                last_error = sanitize_error_message(str(e), self.config.api_key)

                # Non-transient errors (auth, forbidden, not found) fail fast
                if not is_retryable_error(category):
                    return ProviderResponse(
                        raw_text="",
                        model_id=self.config.model_id,
                        provider=self.provider_name,
                        latency_seconds=time.time() - start_time,
                        error=f"{category.value}: {last_error}",
                        error_category=category.value,
                    )

                retries += 1
                if retries <= max_retries:
                    # Exponential backoff capped at 8s
                    backoff = min(1.0 * (2 ** (retries - 1)), 8.0)
                    time.sleep(backoff)

        return ProviderResponse(
            raw_text="",
            model_id=self.config.model_id,
            provider=self.provider_name,
            latency_seconds=time.time() - start_time,
            error=f"{last_category.value if last_category else 'PROVIDER_UNAVAILABLE'} after {max_retries} retries: {last_error}",
            error_category=last_category.value if last_category else ErrorCategory.PROVIDER_UNAVAILABLE.value,
        )
