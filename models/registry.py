"""Model registry and factory for DDIV."""

from __future__ import annotations

from typing import Dict, Optional
from core.config import AgentModelConfig, DDIVConfig, ProviderType
from models.base import ModelConfig, ModelProvider
from models.providers import MockModelProvider, OpenAICompatibleProvider


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
            api_key=agent_config.api_key,
            base_url=self.config.api_base_url,
            temperature=agent_config.temperature,
            max_tokens=agent_config.max_tokens,
            timeout=agent_config.timeout,
            max_retries=agent_config.max_retries,
        )

        if self.config.provider_type == ProviderType.MOCK or self.config.mode == "mock":
            provider = MockModelProvider(model_cfg)
        elif self.config.provider_type == ProviderType.OPENAI_COMPATIBLE:
            provider = OpenAICompatibleProvider(model_cfg)
        else:
            # Fallback to mock if unspecified
            provider = MockModelProvider(model_cfg)

        self._providers[agent_config.name] = provider
        return provider
