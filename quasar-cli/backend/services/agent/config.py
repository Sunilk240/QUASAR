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
    
    # Provider configurations
    PROVIDERS: Dict[str, ProviderConfig] = {
        "ollama": ProviderConfig(
            name="ollama",
            enabled=True,
            base_url="http://localhost:11434",
            models={
                "glm-4.7:cloud": ModelConfig("glm-4.7:cloud", "ollama"),
                "gpt-oss:120b-cloud": ModelConfig("gpt-oss:120b-cloud", "ollama"),
                "qwen3-coder:480b-cloud": ModelConfig("qwen3-coder:480b-cloud", "ollama"),
                "deepseek-v3.1:671b-cloud": ModelConfig("deepseek-v3.1:671b-cloud", "ollama"),
                "deepseek-v3.2:cloud": ModelConfig("deepseek-v3.2:cloud", "ollama"),
            }
        ),
        "cerebras": ProviderConfig(
            name="cerebras",
            enabled=True,
            base_url="https://api.cerebras.ai/v1",
            models={
                "zai-glm-4.7": ModelConfig("zai-glm-4.7", "cerebras"),
                "qwen-3-235b-a22b-instruct-2507": ModelConfig("qwen-3-235b-a22b-instruct-2507", "cerebras"),
            }
        ),
        "groq": ProviderConfig(
            name="groq",
            enabled=True,
            base_url="https://api.groq.com/openai/v1",
            models={
                # NOTE: gpt-oss-120b works well with tool calling
                "openai/gpt-oss-120b": ModelConfig("openai/gpt-oss-120b", "groq"),
                "openai/gpt-oss-20b": ModelConfig("openai/gpt-oss-20b", "groq"),
                # Other Groq models have tool calling issues - use with caution
                "llama-3.3-70b-versatile": ModelConfig("llama-3.3-70b-versatile", "groq"),
                "meta-llama/llama-4-scout-17b-16e-instruct": ModelConfig("meta-llama/llama-4-scout-17b-16e-instruct", "groq"),
            }
        ),
        "cloudflare": ProviderConfig(
            name="cloudflare",
            enabled=False,  # Skipped 
            models={}
        ),
    }
    
    # Task to model mapping (6 tool-aligned categories)
    # Priority: Cerebras → Ollama → Groq (Groq last due to tool calling issues)
    # Only gpt-oss from Groq works well for tools
    TASK_MODELS: Dict[str, List[tuple]] = {
        # File operations - needs reliable tool calling
        "file_operations": [
            ("cerebras", "zai-glm-4.7"),          # Best for tools
            ("ollama", "glm-4.7:cloud"),          # Good fallback
            ("groq", "openai/gpt-oss-120b"),      # Groq's best for tools
        ],
        
        # Search - simple, fast
        "search": [
            ("cerebras", "zai-glm-4.7"),
            ("ollama", "glm-4.7:cloud"),
            ("groq", "openai/gpt-oss-120b"),
        ],
        
        # Execution - suggest commands
        "execution": [
            ("cerebras", "zai-glm-4.7"),
            ("ollama", "glm-4.7:cloud"),
            ("groq", "openai/gpt-oss-120b"),
        ],
        
        # Web - fetch URLs, research
        "web": [
            ("cerebras", "zai-glm-4.7"),
            ("ollama", "glm-4.7:cloud"),
            ("groq", "openai/gpt-oss-120b"),
        ],
        
        # Code Intelligence - explain, analyze
        "code_intelligence": [
            ("cerebras", "zai-glm-4.7"),
            ("ollama", "deepseek-v3.1:671b-cloud"),  # Good for code understanding
            ("groq", "openai/gpt-oss-120b"),
        ],
        
        # General chat - all tools
        "chat": [
            ("cerebras", "zai-glm-4.7"),
            ("ollama", "glm-4.7:cloud"),
            ("groq", "openai/gpt-oss-120b"),
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
    PIP_INSTALL_TIMEOUT = 180         # Extended timeout for pip install commands
    ENABLE_TOOL_CONFIRMATION = False  # Require user confirmation for dangerous ops
    
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
        """Get list of (provider, model_key) for a task type."""
        return cls.TASK_MODELS.get(task_type, [("cerebras", "zai-glm-4.7")])
    
    @classmethod
    def get_provider(cls, provider_name: str) -> Optional[ProviderConfig]:
        """Get provider configuration."""
        return cls.PROVIDERS.get(provider_name)
    
    @classmethod
    def is_provider_enabled(cls, provider_name: str) -> bool:
        """Check if provider is enabled."""
        provider = cls.PROVIDERS.get(provider_name)
        return provider.enabled if provider else False
