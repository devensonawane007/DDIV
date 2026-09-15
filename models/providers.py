"""Concrete ModelProvider implementations: OpenAI-compatible and deterministic Mock."""

from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, Optional, Type
from pydantic import BaseModel

from models.base import ModelConfig, ModelProvider, ProviderResponse


def extract_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    """Robustly extract a JSON object from raw LLM output."""
    text = text.strip()
    # 1. Direct parse attempt
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # 2. Markdown code fence match (```json ... ``` or ``` ...)
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if fence_match:
        try:
            data = json.loads(fence_match.group(1).strip())
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    # 3. Outer brace heuristic
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    return None


class OpenAICompatibleProvider(ModelProvider):
    """Provider for any OpenAI-compatible endpoint (OpenAI, Together, DeepSeek, Ollama, etc.)."""

    def __init__(self, config: ModelConfig):
        super().__init__(config)
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
                api_key = self.config.api_key or "EMPTY"
                base_url = self.config.base_url
                self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=self.config.timeout)
            except ImportError:
                raise RuntimeError("openai package is required for OpenAICompatibleProvider")
        return self._client

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        response_schema: Optional[Type[BaseModel]] = None,
    ) -> ProviderResponse:
        client = self._get_client()
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        schema_instruction = ""
        if response_schema:
            schema_instruction = (
                f"\nYou must respond with a valid JSON object conforming to this schema:\n"
                f"{json.dumps(response_schema.model_json_schema())}\n"
                "Return ONLY the JSON object, no markdown or preamble."
            )
            messages[-1]["content"] += schema_instruction

        start_time = time.time()
        retries = 0
        last_error = None

        while retries <= self.config.max_retries:
            try:
                response = client.chat.completions.create(
                    model=self.config.model_id,
                    messages=messages,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                    response_format={"type": "json_object"} if response_schema else None,
                )
                latency = time.time() - start_time
                content = response.choices[0].message.content or ""
                parsed = extract_json_from_text(content) if response_schema else None

                tokens = response.usage
                prompt_tokens = tokens.prompt_tokens if tokens else 0
                completion_tokens = tokens.completion_tokens if tokens else 0
                total_tokens = tokens.total_tokens if tokens else 0

                return ProviderResponse(
                    raw_text=content,
                    parsed_json=parsed,
                    model_id=self.config.model_id,
                    latency_seconds=latency,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                )
            except Exception as e:
                last_error = str(e)
                retries += 1
                time.sleep(0.5 * (2 ** retries))

        return ProviderResponse(
            raw_text="",
            model_id=self.config.model_id,
            latency_seconds=time.time() - start_time,
            error=f"API call failed after {self.config.max_retries} retries: {last_error}",
        )


class MockModelProvider(ModelProvider):
    """Deterministic mock provider for offline testing and baseline/DDIV validation."""

    def __init__(self, config: ModelConfig, custom_responses: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.custom_responses = custom_responses or {}
        self.call_count = 0
        self.injected_failure_type: Optional[str] = None
        self.injected_recovery_strategy: Optional[str] = None

    def set_injected_scenario(self, failure_type: str, recovery_strategy: str) -> None:
        """Configure mock to trigger a specific failure and corresponding recovery."""
        self.injected_failure_type = failure_type
        self.injected_recovery_strategy = recovery_strategy

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        response_schema: Optional[Type[BaseModel]] = None,
    ) -> ProviderResponse:
        self.call_count += 1
        agent_name = self.config.name

        # Check for explicitly mocked responses
        if agent_name in self.custom_responses:
            data = self.custom_responses[agent_name]
            return ProviderResponse(
                raw_text=json.dumps(data),
                parsed_json=data,
                model_id=self.config.model_id,
                latency_seconds=0.01,
                prompt_tokens=50,
                completion_tokens=50,
                total_tokens=100,
            )

        # Default deterministic role-based responses
        data: Dict[str, Any] = {}

        if agent_name == "Locator":
            data = {
                "relevant_files": ["src/calculator.py", "tests/test_calculator.py"],
                "relevant_symbols": ["Calculator.divide", "validate_inputs"],
                "reasoning_summary": "Located divide method in Calculator class handling division logic.",
                "confidence": 0.88,
            }

        elif agent_name == "Coder":
            # Check if this prompt includes recovery instructions
            is_recovery_attempt = (
                "RECOVERY INSTRUCTIONS" in prompt
                or "TARGETED REPAIR" in prompt
                or "PREVIOUS FAILED ATTEMPTS" in prompt
            )

            if is_recovery_attempt:
                # Repaired valid patch
                patch_content = (
                    "--- a/src/calculator.py\n"
                    "+++ b/src/calculator.py\n"
                    "@@ -5,2 +5,4 @@\n"
                    "     def divide(self, a, b):\n"
                    "+        if b == 0:\n"
                    "+            raise ValueError('Cannot divide by zero')\n"
                    "         return a / b\n"
                )
                data = {
                    "patch": patch_content,
                    "modified_files": ["src/calculator.py"],
                    "reasoning_summary": "Added explicit zero-check raising ValueError as suggested by recovery instructions.",
                    "confidence": 0.94,
                }
            else:
                # Initial attempt: check if we should simulate a specific failure scenario
                if self.injected_failure_type == "F1":
                    # F1: Wrong file modified
                    patch_content = (
                        "--- a/src/unrelated.py\n"
                        "+++ b/src/unrelated.py\n"
                        "@@ -1,1 +1,2 @@\n"
                        "+# unrelated modification\n"
                    )
                    data = {
                        "patch": patch_content,
                        "modified_files": ["src/unrelated.py"],
                        "reasoning_summary": "Modified unrelated utility file.",
                        "confidence": 0.65,
                    }
                elif self.injected_failure_type == "F3":
                    # F3: Malformed patch diff
                    patch_content = "INVALID MALFORMED DIFF WITHOUT PROPER HEADERS\n@@ bad line @@"
                    data = {
                        "patch": patch_content,
                        "modified_files": ["src/calculator.py"],
                        "reasoning_summary": "Generated malformed diff without valid headers.",
                        "confidence": 0.50,
                    }
                else:
                    # Default F2: flawed logic (missing zero check)
                    patch_content = (
                        "--- a/src/calculator.py\n"
                        "+++ b/src/calculator.py\n"
                        "@@ -5,2 +5,3 @@\n"
                        "     def divide(self, a, b):\n"
                        "+        # Flawed logic: does not handle zero denominator\n"
                        "         return a / b\n"
                    )
                    data = {
                        "patch": patch_content,
                        "modified_files": ["src/calculator.py"],
                        "reasoning_summary": "Initial candidate patch modifying divide method without zero protection.",
                        "confidence": 0.72,
                    }

        elif agent_name == "Tester":
            data = {
                "assessment": "Patch modifies division logic in Calculator. Must test division by zero.",
                "suspected_failures": ["ZeroDivisionError on b=0"],
                "recommended_tests": ["test_divide_by_zero", "test_divide_normal"],
                "confidence": 0.89,
            }

        elif agent_name == "Supervisor":
            failure_type = self.injected_failure_type or "F2"
            recovery_strategy = self.injected_recovery_strategy or "A2"
            
            data = {
                "should_retry": True,
                "detected_failure": failure_type,
                "diagnosis": f"Diagnosed {failure_type} based on execution evidence.",
                "recovery_strategy": recovery_strategy,
                "intervention_instructions": f"Apply {recovery_strategy}: re-examine implementation logic and handle edge case.",
                "confidence": 0.85,
            }

        return ProviderResponse(
            raw_text=json.dumps(data),
            parsed_json=data,
            model_id=self.config.model_id,
            latency_seconds=0.01,
            prompt_tokens=120,
            completion_tokens=80,
            total_tokens=200,
        )
