"""Configuration module for DDIV."""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class ExecutionMode(str, Enum):
    MOCK = "mock"
    BASELINE = "baseline"
    DDIV = "ddiv"
    # Ablation modes
    RECOVERY_ONLY = "recovery_only"
    MEMORY_ONLY = "memory_only"
    TRUST_ONLY = "trust_only"
    FULL_DDIV = "full_ddiv"


class ProviderType(str, Enum):
    MOCK = "mock"
    OPENAI_COMPATIBLE = "openai_compatible"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"


class AgentModelConfig(BaseModel):
    name: str
    model: str
    api_key: Optional[str] = None
    temperature: float = 0.2
    max_tokens: int = 2048
    timeout: int = 60
    max_retries: int = 3


class DDIVConfig(BaseModel):
    # Execution
    mode: ExecutionMode = ExecutionMode.MOCK
    experiment_name: str = "default"
    provider_type: ProviderType = ProviderType.MOCK
    api_base_url: Optional[str] = None

    # Agent configs
    locator: AgentModelConfig = Field(
        default_factory=lambda: AgentModelConfig(
            name="Locator",
            model=os.getenv("LOCATOR_MODEL", "Qwen/Qwen2.5-Coder-7B-Instruct"),
            api_key=os.getenv("LOCATOR_API_KEY"),
            temperature=float(os.getenv("LOCATOR_TEMPERATURE", "0.2")),
            max_tokens=int(os.getenv("LOCATOR_MAX_TOKENS", "2048")),
        )
    )
    coder: AgentModelConfig = Field(
        default_factory=lambda: AgentModelConfig(
            name="Coder",
            model=os.getenv("CODER_MODEL", "mistralai/Devstral-24B-v0.1"),
            api_key=os.getenv("CODER_API_KEY"),
            temperature=float(os.getenv("CODER_TEMPERATURE", "0.2")),
            max_tokens=int(os.getenv("CODER_MAX_TOKENS", "4096")),
        )
    )
    tester: AgentModelConfig = Field(
        default_factory=lambda: AgentModelConfig(
            name="Tester",
            model=os.getenv("TESTER_MODEL", "deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct"),
            api_key=os.getenv("TESTER_API_KEY"),
            temperature=float(os.getenv("TESTER_TEMPERATURE", "0.2")),
            max_tokens=int(os.getenv("TESTER_MAX_TOKENS", "2048")),
        )
    )
    supervisor: AgentModelConfig = Field(
        default_factory=lambda: AgentModelConfig(
            name="Supervisor",
            model=os.getenv("SUPERVISOR_MODEL", "Qwen/Qwen2.5-Coder-32B-Instruct"),
            api_key=os.getenv("SUPERVISOR_API_KEY"),
            temperature=float(os.getenv("SUPERVISOR_TEMPERATURE", "0.2")),
            max_tokens=int(os.getenv("SUPERVISOR_MAX_TOKENS", "3072")),
        )
    )

    # Trust Defaults
    init_trust_locator: float = Field(
        default_factory=lambda: float(os.getenv("INIT_TRUST_LOCATOR", "0.87"))
    )
    init_trust_coder: float = Field(
        default_factory=lambda: float(os.getenv("INIT_TRUST_CODER", "0.74"))
    )
    init_trust_tester: float = Field(
        default_factory=lambda: float(os.getenv("INIT_TRUST_TESTER", "0.91"))
    )
    init_trust_supervisor: float = Field(
        default_factory=lambda: float(os.getenv("INIT_TRUST_SUPERVISOR", "0.84"))
    )

    # Workflow constraints
    max_recovery_attempts: int = Field(
        default_factory=lambda: int(os.getenv("MAX_RECOVERY_ATTEMPTS", "4"))
    )
    subprocess_timeout: int = Field(
        default_factory=lambda: int(os.getenv("SUBPROCESS_TIMEOUT", "120"))
    )

    # Paths
    base_dir: Path = Field(default_factory=lambda: Path(os.getcwd()).resolve())
    memory_db_path: Path = Field(
        default_factory=lambda: Path(os.getenv("MEMORY_DB_PATH", "data/ddiv_memory.db"))
    )
    workspace_root: Path = Field(
        default_factory=lambda: Path(os.getenv("WORKSPACE_ROOT", "data/workspaces"))
    )
    logs_dir: Path = Field(default_factory=lambda: Path("logs/runs"))

    @classmethod
    def load_from_env(cls) -> DDIVConfig:
        mode_str = os.getenv("DDIV_MODE", "mock").lower()
        provider_str = os.getenv("PROVIDER_TYPE", "mock").lower()
        api_base_url = os.getenv("API_BASE_URL", "https://api.together.xyz/v1")

        try:
            mode = ExecutionMode(mode_str)
        except ValueError:
            mode = ExecutionMode.MOCK

        try:
            provider_type = ProviderType(provider_str)
        except ValueError:
            provider_type = ProviderType.MOCK

        return cls(
            mode=mode,
            experiment_name=os.getenv("DDIV_EXPERIMENT", "default"),
            provider_type=provider_type,
            api_base_url=api_base_url,
        )
