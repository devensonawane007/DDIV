"""Base abstraction for model providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Type
from pydantic import BaseModel, Field


class ModelConfig(BaseModel):
    name: str
    model_id: str
    provider: str = "mock"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: float = 0.0
    max_tokens: int = 2048
    timeout: int = 120
    max_retries: int = 2


class ProviderResponse(BaseModel):
    raw_text: str
    parsed_json: Optional[Dict[str, Any]] = None
    model_id: str
    provider: Optional[str] = None
    latency_seconds: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    request_id: Optional[str] = None
    error: Optional[str] = None
    error_category: Optional[str] = None


class ModelProvider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, config: ModelConfig):
        self.config = config

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        response_schema: Optional[Type[BaseModel]] = None,
    ) -> ProviderResponse:
        """Synchronously generate a completion for the given prompt."""
        pass

