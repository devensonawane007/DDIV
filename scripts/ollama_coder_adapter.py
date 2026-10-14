"""Ollama Provider Adapter for DDIV Coder Agent.

Provides structured CoderOutput generation using a local Ollama instance
(defaulting to qwen2.5-coder:7b at http://localhost:11434).
Ensures zero silent fallback to cloud models, exact token and latency accounting,
and robust JSON/schema extraction while keeping frozen models/ directory pristine.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Type
import requests
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


class OllamaProvider(ModelProvider):
    """Local Ollama provider adapter for DDIV Coder Agent.

    Guarantees:
    1. Zero Silent Fallback: Failures (connection, timeout, HTTP error, parse error)
       are strictly returned as ProviderResponse errors. No cloud APIs are ever contacted.
    2. Non-Streaming Execution: Uses non-streaming HTTP requests to /api/generate.
    3. Accounting: Accurately records prompt_eval_count, eval_count, total_tokens,
       and latency (derived from total_duration or wall-clock time).
    4. Structured Output Support: Passes format="json" and schema guidelines, then robustly
       parses output for CoderOutput validation.
    """

    DEFAULT_BASE_URL = "http://localhost:11434"
    DEFAULT_MODEL = "qwen2.5-coder:7b"
    DEFAULT_TIMEOUT_SECONDS = 240

    def __init__(
        self,
        config: ModelConfig,
        default_base_url: Optional[str] = None,
    ):
        super().__init__(config)
        self.provider_name = "ollama"
        self.base_url = (
            config.base_url
            or default_base_url
            or os.getenv("OLLAMA_BASE_URL")
            or self.DEFAULT_BASE_URL
        ).rstrip("/")
        self.model_id = (
            config.model_id
            or os.getenv("OLLAMA_MODEL")
            or self.DEFAULT_MODEL
        )
        self.timeout = int(
            config.timeout
            or os.getenv("OLLAMA_TIMEOUT_SECONDS")
            or self.DEFAULT_TIMEOUT_SECONDS
        )
        self.max_retries = max(0, config.max_retries)
        self.max_tokens = config.max_tokens or 4096
        self.temperature = config.temperature

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        response_schema: Optional[Type[BaseModel]] = None,
    ) -> ProviderResponse:
        """Synchronously request generation from local Ollama endpoint."""
        if not self.model_id:
            return ProviderResponse(
                raw_text="",
                model_id="unconfigured",
                provider=self.provider_name,
                error="Model ID is not configured for Ollama.",
                error_category=ErrorCategory.CONFIGURATION_ERROR.value,
            )

        endpoint = f"{self.base_url}/api/generate"
        prompt_content = prompt

        # Append schema instructions if response_schema is provided
        if response_schema:
            schema_json = json.dumps(response_schema.model_json_schema(), indent=2)
            prompt_content = (
                f"{prompt}\n\n"
                f"CRITICAL OUTPUT FORMAT REQUIREMENTS:\n"
                f"You MUST respond ONLY with a valid JSON object matching this schema:\n"
                f"{schema_json}\n\n"
                f"RULES FOR CODE MODIFICATIONS:\n"
                f"1. The 'path' field MUST be an exact relative path from the located files list above. Do NOT use placeholder paths such as 'path/to/file.py'.\n"
                f"2. The 'anchor' field MUST be an exact substring present in that target file.\n"
                f"Do not include any introductory remarks, markdown prose outside the JSON, or conversational preamble."
            )

        payload: Dict[str, Any] = {
            "model": self.model_id,
            "prompt": prompt_content,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
        }

        if system_prompt:
            payload["system"] = system_prompt

        if response_schema:
            payload["format"] = "json"

        start_time = time.time()
        retries = 0
        last_error = ""
        last_category: Optional[ErrorCategory] = None

        while retries <= self.max_retries:
            try:
                res = requests.post(
                    endpoint,
                    json=payload,
                    timeout=self.timeout,
                )

                # Check HTTP status codes
                if res.status_code == 404:
                    cat = ErrorCategory.MODEL_NOT_FOUND
                    err_msg = (
                        f"MODEL_NOT_FOUND: Model '{self.model_id}' was not found in Ollama at {self.base_url}. "
                        f"Please ensure it is pulled using 'ollama pull {self.model_id}'."
                    )
                    return ProviderResponse(
                        raw_text="",
                        model_id=self.model_id,
                        provider=self.provider_name,
                        latency_seconds=time.time() - start_time,
                        error=err_msg,
                        error_category=cat.value,
                    )

                if res.status_code != 200:
                    cat = ErrorCategory.PROVIDER_UNAVAILABLE
                    err_msg = f"HTTP {res.status_code}: {res.text[:200]}"
                    last_category = cat
                    last_error = err_msg
                    retries += 1
                    if retries <= self.max_retries:
                        time.sleep(min(1.0 * (2 ** (retries - 1)), 8.0))
                        continue
                    break

                # HTTP 200 OK
                data = res.json()
                raw_text = (data.get("response") or "").strip()

                # Extract token metrics
                prompt_tokens = int(data.get("prompt_eval_count") or 0)
                completion_tokens = int(data.get("eval_count") or 0)
                total_tokens = prompt_tokens + completion_tokens

                # Extract latency
                total_duration_ns = data.get("total_duration")
                if total_duration_ns and total_duration_ns > 0:
                    latency = total_duration_ns / 1e9
                else:
                    latency = time.time() - start_time

                error_msg: Optional[str] = None
                error_cat: Optional[str] = None
                parsed: Optional[Dict[str, Any]] = None

                if not raw_text:
                    error_msg = "Model returned empty response."
                    error_cat = ErrorCategory.INVALID_RESPONSE.value
                elif response_schema:
                    parsed = robust_extract_json(raw_text)
                    if parsed is None:
                        error_msg = f"JSON_PARSE_ERROR: Failed to extract valid JSON matching schema from output: {raw_text[:200]}"
                        error_cat = ErrorCategory.INVALID_RESPONSE.value

                return ProviderResponse(
                    raw_text=raw_text,
                    parsed_json=parsed,
                    model_id=self.model_id,
                    provider=self.provider_name,
                    latency_seconds=latency,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    error=error_msg,
                    error_category=error_cat,
                )

            except requests.exceptions.Timeout as e:
                last_category = ErrorCategory.TIMEOUT
                last_error = f"TIMEOUT: Ollama request timed out after {self.timeout}s: {sanitize_error_message(str(e))}"
                retries += 1
                if retries <= self.max_retries:
                    time.sleep(min(1.0 * (2 ** (retries - 1)), 8.0))
                    continue
                break

            except requests.exceptions.ConnectionError as e:
                # Connection refused or host unreachable -> Fail immediately without useless retry
                last_category = ErrorCategory.PROVIDER_UNAVAILABLE
                last_error = (
                    f"PROVIDER_UNAVAILABLE: Connection refused at {self.base_url}. "
                    f"Ensure local Ollama server is running. Details: {sanitize_error_message(str(e))}"
                )
                return ProviderResponse(
                    raw_text="",
                    model_id=self.model_id,
                    provider=self.provider_name,
                    latency_seconds=time.time() - start_time,
                    error=last_error,
                    error_category=last_category.value,
                )

            except Exception as e:
                status_code = getattr(getattr(e, "response", None), "status_code", None)
                category = categorize_error(e, status_code)
                last_category = category
                last_error = sanitize_error_message(str(e))

                if not is_retryable_error(category):
                    return ProviderResponse(
                        raw_text="",
                        model_id=self.model_id,
                        provider=self.provider_name,
                        latency_seconds=time.time() - start_time,
                        error=f"{category.value}: {last_error}",
                        error_category=category.value,
                    )

                retries += 1
                if retries <= self.max_retries:
                    time.sleep(min(1.0 * (2 ** (retries - 1)), 8.0))
                    continue
                break

        # If retries exhausted
        return ProviderResponse(
            raw_text="",
            model_id=self.model_id,
            provider=self.provider_name,
            latency_seconds=time.time() - start_time,
            error=f"{last_category.value if last_category else 'PROVIDER_UNAVAILABLE'} after {self.max_retries} retries: {last_error}",
            error_category=last_category.value if last_category else ErrorCategory.PROVIDER_UNAVAILABLE.value,
        )


def register_ollama_provider():
    """Hook ModelRegistry dynamically to route 'ollama' agent configs to OllamaProvider."""
    from models.registry import ModelRegistry
    orig_get_provider = ModelRegistry.get_provider_for_agent

    def patched_get_provider(self, agent_config):
        if agent_config.name in self._providers:
            return self._providers[agent_config.name]

        if agent_config.provider.lower() == "ollama":
            model_cfg = ModelConfig(
                name=agent_config.name,
                model_id=agent_config.model,
                provider=agent_config.provider,
                api_key=agent_config.api_key,
                base_url=agent_config.base_url or self.config.api_base_url,
                temperature=agent_config.temperature,
                max_tokens=agent_config.max_tokens,
                timeout=agent_config.timeout,
                max_retries=agent_config.max_retries,
            )
            provider = OllamaProvider(model_cfg)
            self._providers[agent_config.name] = provider
            return provider

        return orig_get_provider(self, agent_config)

    ModelRegistry.get_provider_for_agent = patched_get_provider
