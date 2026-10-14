"""Configuration module for DDIV."""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field

try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except ImportError:
    pass


class ExecutionMode(str, Enum):
    MOCK = "mock"
    BASELINE = "baseline"
    DDIV = "ddiv"
    REAL = "real"
    # Ablation modes
    RECOVERY_ONLY = "recovery_only"
    MEMORY_ONLY = "memory_only"
    TRUST_ONLY = "trust_only"
    FULL_DDIV = "full_ddiv"


# Frozen Dynamic Trust Hyperparameters
TRUST_SUCCESS_DELTA: float = float(os.getenv("TRUST_SUCCESS_DELTA", "0.05"))
TRUST_FAILURE_DELTA: float = float(os.getenv("TRUST_FAILURE_DELTA", "0.08"))
TRUST_REGRESSION_DELTA: float = float(os.getenv("TRUST_REGRESSION_DELTA", "0.10"))


class ProviderType(str, Enum):
    MOCK = "mock"
    GEMINI = "gemini"
    XAI = "xai"
    GROQ = "groq"
    OPENROUTER = "openrouter"
    HUGGINGFACE = "huggingface"
    OPENAI_COMPATIBLE = "openai_compatible"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"


class AgentModelConfig(BaseModel):
    name: str
    provider: str = "mock"
    model: str = ""
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: float = 0.0
    max_tokens: int = 2048
    timeout: int = 120
    max_retries: int = 2


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
            provider=os.getenv("LOCATOR_PROVIDER", "gemini"),
            model=os.getenv("LOCATOR_MODEL", ""),
            api_key=os.getenv("GEMINI_API_KEY") or os.getenv("LOCATOR_API_KEY"),
            base_url=os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"),
            temperature=float(os.getenv("LOCATOR_TEMPERATURE", os.getenv("MODEL_TEMPERATURE", "0.0"))),
            max_tokens=int(os.getenv("LOCATOR_MAX_TOKENS", "2048")),
            timeout=int(os.getenv("MODEL_TIMEOUT_SECONDS", os.getenv("REQUEST_TIMEOUT", "120"))),
            max_retries=int(os.getenv("MODEL_MAX_RETRIES", os.getenv("MAX_RETRIES", "2"))),
        )
    )
    coder: AgentModelConfig = Field(
        default_factory=lambda: (
            AgentModelConfig(
                name="Coder",
                provider="ollama",
                model=os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b"),
                api_key="ollama",
                base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
                temperature=float(os.getenv("CODER_TEMPERATURE", os.getenv("MODEL_TEMPERATURE", "0.0"))),
                max_tokens=int(os.getenv("CODER_MAX_TOKENS", "4096")),
                timeout=int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "240")),
                max_retries=int(os.getenv("MODEL_MAX_RETRIES", os.getenv("MAX_RETRIES", "2"))),
            )
            if os.getenv("DDIV_CODER_PROVIDER", "").lower() == "ollama"
            else AgentModelConfig(
                name="Coder",
                provider=os.getenv("CODER_PROVIDER", "groq"),
                model=os.getenv("CODER_MODEL", ""),
                api_key=os.getenv("GROQ_API_KEY") or os.getenv("XAI_API_KEY") or os.getenv("CODER_API_KEY"),
                base_url=(
                    os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
                    if os.getenv("CODER_PROVIDER", "groq").lower() == "groq"
                    else os.getenv("XAI_BASE_URL", "https://api.x.ai/v1")
                ),
                temperature=float(os.getenv("CODER_TEMPERATURE", os.getenv("MODEL_TEMPERATURE", "0.0"))),
                max_tokens=int(os.getenv("CODER_MAX_TOKENS", "4096")),
                timeout=int(os.getenv("MODEL_TIMEOUT_SECONDS", os.getenv("REQUEST_TIMEOUT", "120"))),
                max_retries=int(os.getenv("MODEL_MAX_RETRIES", os.getenv("MAX_RETRIES", "2"))),
            )
        )
    )
    tester: AgentModelConfig = Field(
        default_factory=lambda: AgentModelConfig(
            name="Tester",
            provider=os.getenv("TESTER_PROVIDER", "openrouter"),
            model=os.getenv("TESTER_MODEL", ""),
            api_key=(
                os.getenv("GROQ_API_KEY")
                if os.getenv("TESTER_PROVIDER", "").lower() == "groq"
                else (os.getenv("OPENROUTER_API_KEY") or os.getenv("TESTER_API_KEY"))
            ),
            base_url=(
                os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
                if os.getenv("TESTER_PROVIDER", "").lower() == "groq"
                else os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
            ),
            temperature=float(os.getenv("TESTER_TEMPERATURE", os.getenv("MODEL_TEMPERATURE", "0.0"))),
            max_tokens=int(os.getenv("TESTER_MAX_TOKENS", "2048")),
            timeout=int(os.getenv("MODEL_TIMEOUT_SECONDS", os.getenv("REQUEST_TIMEOUT", "120"))),
            max_retries=int(os.getenv("MODEL_MAX_RETRIES", os.getenv("MAX_RETRIES", "2"))),
        )
    )
    supervisor: AgentModelConfig = Field(
        default_factory=lambda: AgentModelConfig(
            name="Supervisor",
            provider=os.getenv("SUPERVISOR_PROVIDER", "huggingface"),
            model=os.getenv("SUPERVISOR_MODEL", ""),
            api_key=(
                os.getenv("GROQ_API_KEY")
                if os.getenv("SUPERVISOR_PROVIDER", "").lower() == "groq"
                else (
                    os.getenv("OPENROUTER_API_KEY") or os.getenv("SUPERVISOR_API_KEY")
                    if os.getenv("SUPERVISOR_PROVIDER", "").lower() == "openrouter"
                    else (os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_API_KEY") or os.getenv("SUPERVISOR_API_KEY"))
                )
            ),
            base_url=(
                os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
                if os.getenv("SUPERVISOR_PROVIDER", "").lower() == "groq"
                else (
                    os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
                    if os.getenv("SUPERVISOR_PROVIDER", "").lower() == "openrouter"
                    else os.getenv("HF_BASE_URL", "https://router.huggingface.co/v1")
                )
            ),
            temperature=float(os.getenv("SUPERVISOR_TEMPERATURE", os.getenv("MODEL_TEMPERATURE", "0.0"))),
            max_tokens=int(os.getenv("SUPERVISOR_MAX_TOKENS", "3072")),
            timeout=int(os.getenv("MODEL_TIMEOUT_SECONDS", os.getenv("REQUEST_TIMEOUT", "120"))),
            max_retries=int(os.getenv("MODEL_MAX_RETRIES", os.getenv("MAX_RETRIES", "2"))),
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

    def get_experiment_metadata(self) -> Dict[str, Any]:
        """Return audit-safe metadata for research reproducibility (zero credentials)."""
        return {
            "mode": self.mode.value,
            "experiment_name": self.experiment_name,
            "global_parameters": {
                "temperature": float(os.getenv("MODEL_TEMPERATURE", "0.0")),
                "max_retries": int(os.getenv("MODEL_MAX_RETRIES", "2")),
                "timeout_seconds": int(os.getenv("MODEL_TIMEOUT_SECONDS", "120")),
            },
            "agents": {
                "Locator": {
                    "provider": self.locator.provider,
                    "model_id": self.locator.model,
                    "endpoint": self.locator.base_url,
                    "temperature": self.locator.temperature,
                    "max_tokens": self.locator.max_tokens,
                    "max_retries": self.locator.max_retries,
                    "timeout": self.locator.timeout,
                },
                "Coder": {
                    "provider": self.coder.provider,
                    "model_id": self.coder.model,
                    "endpoint": self.coder.base_url,
                    "temperature": self.coder.temperature,
                    "max_tokens": self.coder.max_tokens,
                    "max_retries": self.coder.max_retries,
                    "timeout": self.coder.timeout,
                },
                "Tester": {
                    "provider": self.tester.provider,
                    "model_id": self.tester.model,
                    "endpoint": self.tester.base_url,
                    "temperature": self.tester.temperature,
                    "max_tokens": self.tester.max_tokens,
                    "max_retries": self.tester.max_retries,
                    "timeout": self.tester.timeout,
                },
                "Supervisor": {
                    "provider": self.supervisor.provider,
                    "model_id": self.supervisor.model,
                    "endpoint": self.supervisor.base_url,
                    "temperature": self.supervisor.temperature,
                    "max_tokens": self.supervisor.max_tokens,
                    "max_retries": self.supervisor.max_retries,
                    "timeout": self.supervisor.timeout,
                },
            },
        }

    def validate_for_execution(self) -> None:
        """Validate that all required real providers have explicit models and credentials configured."""
        if self.mode == ExecutionMode.MOCK:
            return

        def get_key_var(prov: str, default: str) -> str:
            p = prov.lower()
            if p == "groq":
                return "GROQ_API_KEY"
            if p == "gemini":
                return "GEMINI_API_KEY"
            if p == "openrouter":
                return "OPENROUTER_API_KEY"
            if p == "huggingface":
                return "HF_TOKEN"
            return default

        agents = [
            ("Locator", self.locator, "LOCATOR_MODEL", get_key_var(self.locator.provider, "GEMINI_API_KEY")),
            ("Coder", self.coder, "CODER_MODEL", get_key_var(self.coder.provider, "GROQ_API_KEY")),
            ("Tester", self.tester, "TESTER_MODEL", get_key_var(self.tester.provider, "OPENROUTER_API_KEY")),
            ("Supervisor", self.supervisor, "SUPERVISOR_MODEL", get_key_var(self.supervisor.provider, "OPENROUTER_API_KEY")),
        ]

        for name, cfg, model_var, key_var in agents:
            if cfg.provider.lower() == "mock":
                continue

            if not cfg.model or cfg.model.startswith("REPLACE_") or "<" in cfg.model:
                raise ValueError(
                    f"Configuration Error: Missing or placeholder model ID for {name} Agent. "
                    f"Please configure {model_var} in .env with a valid, verified model ID."
                )

            if cfg.provider.lower() == "ollama":
                continue

            if not cfg.api_key:
                raise ValueError(
                    f"Configuration Error: Missing API key/token for {name} Agent ({cfg.provider}). "
                    f"Please configure {key_var} in .env."
                )

    @classmethod
    def load_from_env(cls) -> DDIVConfig:
        mode_str = os.getenv("DDIV_MODE", "mock").lower()
        provider_str = os.getenv("PROVIDER_TYPE", "mock").lower()
        api_base_url = os.getenv("API_BASE_URL", "https://api.together.xyz/v1")

        if mode_str == "real":
            mode = ExecutionMode.DDIV
        else:
            try:
                mode = ExecutionMode(mode_str)
            except ValueError:
                mode = ExecutionMode.MOCK

        try:
            provider_type = ProviderType(provider_str)
        except ValueError:
            provider_type = ProviderType.MOCK

        if os.getenv("DDIV_CODER_PROVIDER", "").lower() == "ollama":
            try:
                from scripts.ollama_coder_adapter import register_ollama_provider
                register_ollama_provider()
            except ImportError:
                pass

        return cls(
            mode=mode,
            experiment_name=os.getenv("DDIV_EXPERIMENT", "default"),
            provider_type=provider_type,
            api_base_url=api_base_url,
        )

