"""Base agent class with structured input/output validation and observability."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Generic, Optional, Type, TypeVar
from pydantic import BaseModel, Field

from models.base import ModelProvider, ProviderResponse

T_Output = TypeVar("T_Output", bound=BaseModel)


class AgentInputMetadata(BaseModel):
    task_id: str
    run_id: str
    attempt: int = 1
    extra_context: Dict[str, Any] = Field(default_factory=dict)


class AgentExecutionResult(BaseModel, Generic[T_Output]):
    task_id: str
    run_id: str
    agent_id: str
    attempt: int
    timestamp: float = Field(default_factory=time.time)
    output: Optional[T_Output] = None
    raw_response: str = ""
    confidence: float = 0.0
    latency_seconds: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    error: Optional[str] = None
    success: bool = True


class BaseAgent(ABC, Generic[T_Output]):
    """Abstract agent handling provider invocation, validation, and retry."""

    def __init__(self, agent_id: str, provider: ModelProvider, output_schema: Type[T_Output]):
        self.agent_id = agent_id
        self.provider = provider
        self.output_schema = output_schema

    @abstractmethod
    def build_prompt(self, input_data: Dict[str, Any], metadata: AgentInputMetadata) -> str:
        """Construct the prompt from input context."""
        pass

    @abstractmethod
    def build_system_prompt(self) -> str:
        """System prompt defining the role and expectations."""
        pass

    def execute(self, input_data: Dict[str, Any], metadata: AgentInputMetadata) -> AgentExecutionResult[T_Output]:
        """Execute the agent and validate output against output_schema."""
        prompt = self.build_prompt(input_data, metadata)
        system_prompt = self.build_system_prompt()

        start_time = time.time()
        provider_resp: ProviderResponse = self.provider.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            response_schema=self.output_schema,
        )
        latency = time.time() - start_time

        if provider_resp.error:
            return AgentExecutionResult(
                task_id=metadata.task_id,
                run_id=metadata.run_id,
                agent_id=self.agent_id,
                attempt=metadata.attempt,
                raw_response=provider_resp.raw_text,
                latency_seconds=latency,
                error=provider_resp.error,
                success=False,
            )

        parsed_obj: Optional[T_Output] = None
        error_msg: Optional[str] = None

        if provider_resp.parsed_json:
            try:
                parsed_obj = self.output_schema.model_validate(provider_resp.parsed_json)
            except Exception as val_err:
                error_msg = f"Schema validation error: {str(val_err)}"
        else:
            error_msg = f"Failed to extract valid JSON matching schema from response: {provider_resp.raw_text[:200]}"

        confidence = getattr(parsed_obj, "confidence", 0.0) if parsed_obj else 0.0

        return AgentExecutionResult(
            task_id=metadata.task_id,
            run_id=metadata.run_id,
            agent_id=self.agent_id,
            attempt=metadata.attempt,
            output=parsed_obj,
            raw_response=provider_resp.raw_text,
            confidence=confidence,
            latency_seconds=provider_resp.latency_seconds or latency,
            prompt_tokens=provider_resp.prompt_tokens,
            completion_tokens=provider_resp.completion_tokens,
            total_tokens=provider_resp.total_tokens,
            error=error_msg,
            success=(parsed_obj is not None),
        )
