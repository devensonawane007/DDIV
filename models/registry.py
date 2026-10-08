"""Model registry and factory for DDIV."""

from __future__ import annotations

from typing import Dict, Optional
from core.config import AgentModelConfig, DDIVConfig, ExecutionMode, ProviderType
from models.base import ModelConfig, ModelProvider
from models.providers import (
    GeminiProvider,
    GroqProvider,
    HuggingFaceProvider,
    MockModelProvider,
    OpenAICompatibleProvider,
    OpenRouterProvider,
    XAIProvider,
)


class ModelRegistry:
    """Factory and registry to supply model providers for agents."""

    def __init__(self, config: DDIVConfig):
        self.config = config
        self._providers: Dict[str, ModelProvider] = {}

    def get_provider_for_agent(self, agent_config: AgentModelConfig) -> ModelProvider:
        """Create or return cached provider for an agent."""
        if agent_config.name in self._providers:
            return self._providers[agent_config.name]

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

        # In mock execution mode, or if agent provider is mock, use MockModelProvider
        if (
            self.config.provider_type == ProviderType.MOCK
            or self.config.mode == ExecutionMode.MOCK
            or agent_config.provider.lower() == "mock"
        ):
            provider = MockModelProvider(model_cfg)
        else:
            prov_type = agent_config.provider.lower()
            if prov_type == "gemini":
                provider = GeminiProvider(model_cfg)
            elif prov_type == "xai":
                provider = XAIProvider(model_cfg)
            elif prov_type == "groq":
                provider = GroqProvider(model_cfg)
            elif prov_type == "openrouter":
                provider = OpenRouterProvider(model_cfg)
            elif prov_type == "huggingface":
                provider = HuggingFaceProvider(model_cfg)
            elif prov_type in ("openai_compatible", "openai"):
                provider = OpenAICompatibleProvider(model_cfg)
            else:
                provider = MockModelProvider(model_cfg)

        self._providers[agent_config.name] = provider
        return provider
