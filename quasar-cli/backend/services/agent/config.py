"""
AI Agent Configuration

Centralized configuration for:
- Model names per provider
- Task-to-model mappings
- Default settings

Easy to modify for new models.
"""

from typing import Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class ModelConfig:
    """Configuration for a single model."""
    name: str
    provider: str
    temperature: float = 0.7
    max_tokens: int = 4096
    

@dataclass
class ProviderConfig:
    """Configuration for a provider."""
    name: str
    enabled: bool = True
    base_url: Optional[str] = None
    models: Dict[str, ModelConfig] = field(default_factory=dict)


class AgentConfig:
    """
    Centralized agent configuration.
    
    Configurable and scalable - easy to add new models/providers.
    
    Model Priority (for tool calling):
    1. Cerebras - Best for tool calling, fast inference
    2. Ollama - Local models, good tool calling
    3. Groq - LAST RESORT (tool calling issues with some models)
    """
    
    # ─────────────────────────────────────────────────────────────────────
    # PROVIDERS — two built-in + up to 4 user-defined custom slots.
    #
    # 1. ollama     — Ollama server (cloud-tagged models via OLLAMA_BASE_URL).
    # 2. custom_1   — Primary provider   (fastest / best for most tasks)
    # 3. custom_2   — Secondary provider (large context / code specialist)
    # 4. custom_3   — Third provider     (fallback / alternate)
    # 5. custom_4   — Fourth provider    (spare / classification only)
    #
    # Each custom slot reads three env vars at runtime:
    #   CUSTOM_N_BASE_URL   e.g. https://api.cerebras.ai/v1
    #   CUSTOM_N_MODEL      e.g. zai-glm-4.7
    #   CUSTOM_N_API_KEY_1  (plus _2 for rotation)
    # If CUSTOM_N_BASE_URL is not set, that slot is silently skipped.
    # ─────────────────────────────────────────────────────────────────────
    PROVIDERS: Dict[str, ProviderConfig] = {
        "ollama": ProviderConfig(
            name="ollama",
            enabled=True,
            base_url="http://localhost:11434",   # overridden by OLLAMA_BASE_URL env var
            models={
                "glm-4.7:cloud":             ModelConfig("glm-4.7:cloud",             "ollama"),
                "gpt-oss:120b-cloud":         ModelConfig("gpt-oss:120b-cloud",         "ollama"),
                "qwen3-coder:480b-cloud":     ModelConfig("qwen3-coder:480b-cloud",     "ollama"),
                "deepseek-v3.1:671b-cloud":   ModelConfig("deepseek-v3.1:671b-cloud",   "ollama"),
                "deepseek-v3.2:cloud":        ModelConfig("deepseek-v3.2:cloud",        "ollama"),
            }
        ),

        # Custom slots — base_url=None means: read from CUSTOM_N_BASE_URL at runtime.
        "custom_1": ProviderConfig(name="custom_1", enabled=True, base_url=None, models={}),
        "custom_2": ProviderConfig(name="custom_2", enabled=True, base_url=None, models={}),
        "custom_3": ProviderConfig(name="custom_3", enabled=True, base_url=None, models={}),
        "custom_4": ProviderConfig(name="custom_4", enabled=True, base_url=None, models={}),
    }


    # Task to model mapping
    # Architecture: Ollama (always) + up to 4 custom slots (each its own API).
    # Assign each task type to the most appropriate slot.
    # Slots not configured in .env are transparently skipped by the router.
    #
    # Sentinel "__env__" is resolved to CUSTOM_N_MODEL at call time by
    # get_models_for_task(). N is the slot number (1-4).
    TASK_MODELS: Dict[str, List[tuple]] = {
        # File operations — solid tool-calling + long context
        "file_operations": [
            ("custom_2", "__env__"),       # Slot 2: large-context / code model
            ("custom_1", "__env__"),       # Slot 1: fast primary
            ("ollama",   "glm-4.7:cloud"), # Ollama fallback
            ("custom_3", "__env__"),
            ("custom_4", "__env__"),
        ],

        # Search — lightweight and fast
        "search": [
            ("custom_1", "__env__"),
            ("ollama",   "glm-4.7:cloud"),
            ("custom_2", "__env__"),
            ("custom_3", "__env__"),
            ("custom_4", "__env__"),
        ],

        # Execution — run_command / suggest_command
        "execution": [
            ("custom_1", "__env__"),
            ("ollama",   "glm-4.7:cloud"),
            ("custom_2", "__env__"),
            ("custom_3", "__env__"),
            ("custom_4", "__env__"),
        ],

        # Web — URL fetch and research
        "web": [
            ("custom_1", "__env__"),
            ("ollama",   "glm-4.7:cloud"),
            ("custom_3", "__env__"),
            ("custom_4", "__env__"),
        ],

        # Code Intelligence — biggest/best code model first
        "code_intelligence": [
            ("custom_2", "__env__"),                    # Slot 2: code specialist
            ("ollama",   "deepseek-v3.1:671b-cloud"),   # Large Ollama
            ("custom_1", "__env__"),
            ("ollama",   "glm-4.7:cloud"),
            ("custom_3", "__env__"),
            ("custom_4", "__env__"),
        ],

        # General chat — all tools enabled, any fast model
        "chat": [
            ("custom_1", "__env__"),
            ("ollama",   "glm-4.7:cloud"),
            ("custom_2", "__env__"),
            ("custom_3", "__env__"),
            ("custom_4", "__env__"),
        ],

        # Task classification — fastest possible (small model is fine)
        "classification": [
            ("custom_4", "__env__"),       # Slot 4: designated fast/cheap model
            ("custom_1", "__env__"),
            ("ollama",   "glm-4.7:cloud"),
            ("custom_2", "__env__"),
            ("custom_3", "__env__"),
        ],
    }
    
    # Default settings
    DEFAULT_TEMPERATURE = 0.7
    DEFAULT_MAX_TOKENS = 4096
    MAX_RETRIES = 3
    TIMEOUT_SECONDS = 60
    
    # Agentic Loop Configuration
    MAX_TOOL_ITERATIONS = 30          # Max tool call loops per request
    TOOL_TIMEOUT_SECONDS = 180        # Timeout per individual tool execution
    SESSION_TIMEOUT_SECONDS = 600     # Max total time per query (10 min) — configurable
    PIP_INSTALL_TIMEOUT = 180         # Extended timeout for pip install commands
    ENABLE_TOOL_CONFIRMATION = True   # Require user confirmation for non-safe commands
    
    # Tool Output Limits (prevents context overflow)
    MAX_FILE_CONTENT_CHARS = 30000    # ~7.5K tokens per file read
    MAX_OTHER_RESULT_CHARS = 10000    # ~2.5K tokens for other results
    MAX_FILE_LINES = 2000             # Files larger than this return metadata only
    MAX_SEARCH_RESULTS = 50           # Max files returned by search
    MAX_SEARCH_MATCHES = 100          # Max matches returned by grep
    MAX_URL_CHARS = 8000              # Max chars extracted from URLs
    MAX_HISTORY_SIZE = 20             # Max tool results kept in memory
    
    # Timeouts
    MCP_TIMEOUT = 30.0                # MCP server call timeout
    URL_FETCH_TIMEOUT = 10.0          # HTTP request timeout
    
    # All task types use tools now
    TOOL_ENABLED_TASKS = [
        "file_operations",
        "search",
        "execution",
        "web",
        "code_intelligence",
        "chat",
    ]
    
    # No read-only tasks - all can use tools
    READ_ONLY_TASKS = []
    
    @classmethod
    def get_models_for_task(cls, task_type: str) -> List[tuple]:
        """
        Get list of (provider, model_key) for a task type.

        Resolves the "__env__" sentinel to the slot-specific CUSTOM_N_MODEL env var.
        For example:
          ("custom_1", "__env__")  →  CUSTOM_1_MODEL  →  ("custom_1", "zai-glm-4.7")
          ("custom_2", "__env__")  →  CUSTOM_2_MODEL  →  ("custom_2", "deepseek-v3-5")
        Slots without a CUSTOM_N_BASE_URL configured are silently dropped.
        """
        import os
        chain = cls.TASK_MODELS.get(task_type, [("ollama", "glm-4.7:cloud")])

        resolved = []
        for provider, model_key in chain:
            if model_key == "__env__":
                # Extract slot number: "custom_1" → "1", "custom_2" → "2"
                slot = provider.split("_", 1)[1] if "_" in provider else ""
                env_prefix = f"CUSTOM_{slot.upper()}_" if slot else "CUSTOM_"

                base_url = os.getenv(f"{env_prefix}BASE_URL", "").strip()
                model_name = os.getenv(f"{env_prefix}MODEL", "").strip()

                if base_url and model_name:
                    resolved.append((provider, model_name))
                # else: slot not configured — silently skip
            else:
                resolved.append((provider, model_key))
        return resolved
    
    @classmethod
    def get_provider(cls, provider_name: str) -> Optional[ProviderConfig]:
        """Get provider configuration."""
        return cls.PROVIDERS.get(provider_name)
    
    @classmethod
    def is_provider_enabled(cls, provider_name: str) -> bool:
        """Check if provider is enabled."""
        provider = cls.PROVIDERS.get(provider_name)
        return provider.enabled if provider else False
