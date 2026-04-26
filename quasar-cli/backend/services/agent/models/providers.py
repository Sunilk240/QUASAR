"""
LangChain Model Providers

Architecture: ALL providers (Cerebras, Groq, Cloudflare, custom, …) share
a single implementation — get_openai_compatible_model() — because every cloud
inference endpoint we use is OpenAI API-compatible.

get_model() is fully generic:
  1. Reads the provider's base_url from AgentConfig (the default)
  2. Lets the user override it with {PROVIDER_UPPER}_BASE_URL env var
  3. Gets the api_key from CredentialManager
  4. Routes Ollama → ChatOllama (different SDK), everything else → ChatOpenAI

To add a new provider:
  - Add it to AgentConfig.PROVIDERS with a base_url
  - Add env vars:  {PROVIDER_UPPER}_BASE_URL, {PROVIDER_UPPER}_API_KEY_1 (optional _2)
  - That's it. No code changes needed here.
"""

import os
from typing import Optional, Any
from .credentials import CredentialManager
import logging

logger = logging.getLogger("providers")


class ModelProviders:
    """
    Factory for creating LangChain model instances.

    Public API:
        get_model(provider, model_name, temperature, **kwargs)  ← use this
        get_openai_compatible_model(base_url, api_key, model_name, …)
        get_ollama_model(model_name, temperature, …)            ← Ollama exception
    """

    def __init__(self):
        self.cred_manager = CredentialManager()
        logger.debug("ModelProviders initialized")

    # -----------------------------------------------------------------------
    # Core implementation — the only function that creates a ChatModel
    # -----------------------------------------------------------------------

    def get_openai_compatible_model(
        self,
        base_url: str,
        api_key: str,
        model_name: str,
        temperature: float = 0.7,
        **kwargs,
    ) -> Optional[Any]:
        """
        Universal adapter for any OpenAI-compatible endpoint.

        Works with every cloud inference API:
          Cerebras, Groq, Cloudflare, SambaNova, OpenRouter, Together AI,
          GitHub Models, LM Studio, vLLM, or any custom server.

        Args:
            base_url:    Full API base URL, e.g. https://api.cerebras.ai/v1
            api_key:     API key. Use 'not-needed' for key-less local servers.
            model_name:  Model identifier the server recognises
            temperature: Sampling temperature

        Returns:
            ChatOpenAI instance, or None on error
        """
        if not base_url:
            logger.warning("⚠️ get_openai_compatible_model: base_url is empty — skipping")
            return None
        try:
            from langchain_openai import ChatOpenAI
            model = ChatOpenAI(
                base_url=base_url,
                api_key=api_key or "not-needed",
                model=model_name,
                temperature=temperature,
                **kwargs,
            )
            logger.info(f"✅ OpenAI-compatible model: {base_url} / {model_name}")
            return model
        except ImportError:
            logger.error("❌ langchain-openai not installed — cannot create model")
            return None
        except Exception as exc:
            logger.error(f"❌ Error creating OpenAI-compatible model: {exc}")
            return None

    # -----------------------------------------------------------------------
    # Ollama — only special case (uses ChatOllama, not ChatOpenAI)
    # -----------------------------------------------------------------------

    def get_ollama_model(
        self,
        model_name: str = "glm-4.7:cloud",
        temperature: float = 0.7,
        **kwargs,
    ) -> Optional[Any]:
        """
        Get an Ollama model.

        Base URL priority:
          1. OLLAMA_BASE_URL env var
          2. ollama_url user setting (set by CLI on startup)
          3. Hardcoded default: http://localhost:11434

        Args:
            model_name:  Ollama model tag, e.g. "glm-4.7:cloud"
            temperature: Sampling temperature

        Returns:
            ChatOllama instance, or None on error
        """
        base_url = (
            os.getenv("OLLAMA_BASE_URL")
            or self.cred_manager.get_setting("ollama_url", "http://localhost:11434")
        )
        logger.info(f"🦙 Creating Ollama model: {model_name} at {base_url}")
        try:
            from langchain_ollama import ChatOllama
            model = ChatOllama(
                model=model_name,
                base_url=base_url,
                temperature=temperature,
                **kwargs,
            )
            logger.info(f"✅ Ollama model created: {model_name}")
            return model
        except ImportError:
            logger.error("❌ langchain-ollama not installed")
            return None
        except Exception as exc:
            logger.error(f"❌ Error creating Ollama model: {exc}")
            return None

    # -----------------------------------------------------------------------
    # Generic dispatcher — the only public entry point for all other code
    # -----------------------------------------------------------------------

    def get_model(
        self,
        provider: str,
        model_name: str,
        temperature: float = 0.7,
        **kwargs,
    ) -> Optional[Any]:
        """
        Get a model by provider name. Fully generic — no hardcoded providers.

        Resolution order for base_url:
          1. {PROVIDER_UPPER}_BASE_URL env var  (e.g. CEREBRAS_BASE_URL)
          2. AgentConfig.PROVIDERS[provider].base_url  (the registered default)

        Resolution order for api_key:
          1. CredentialManager (from .env CEREBRAS_API_KEY_1 etc.)
          2. {PROVIDER_UPPER}_API_KEY env var  (single-key fallback)
          3. 'not-needed'  (for key-less local servers)

        Special case: 'ollama' routes to get_ollama_model() because it uses
        ChatOllama (langchain-ollama), not ChatOpenAI.

        Args:
            provider:    Provider name — 'ollama' or 'custom'
                         (ollama = ChatOllama; custom = any OpenAI-compatible endpoint)
            model_name:  Model identifier
            temperature: Sampling temperature

        Returns:
            ChatModel instance, or None if provider not configured / no base_url
        """
        logger.info(f"🔧 get_model: provider={provider}, model={model_name}")

        # Ollama is the only exception — different SDK
        if provider == "ollama":
            return self.get_ollama_model(model_name, temperature, **kwargs)

        # --- Generic path for all OpenAI-compatible providers ---

        # 1. Resolve base_url
        # For custom_N slots, the env var is CUSTOM_N_BASE_URL (e.g. CUSTOM_1_BASE_URL).
        # For a plain "custom" provider, it falls back to CUSTOM_BASE_URL.
        from ..config import AgentConfig
        provider_config = AgentConfig.get_provider(provider)

        # Derive env var prefix: "custom_1" → "CUSTOM_1_", "custom" → "CUSTOM_"
        if provider.startswith("custom"):
            parts = provider.split("_", 1)
            slot = parts[1] if len(parts) > 1 else ""
            env_prefix = f"CUSTOM_{slot.upper()}_" if slot else "CUSTOM_"
        else:
            env_prefix = f"{provider.upper()}_"

        env_base_url_key = f"{env_prefix}BASE_URL"
        base_url = (
            os.getenv(env_base_url_key)                                    # env override first
            or (provider_config.base_url if provider_config else None)     # config default
        )

        if not base_url:
            logger.warning(
                f"⚠️ No base_url for provider '{provider}'. "
                f"Set {env_base_url_key} in your .env or terminal."
            )
            return None

        # 2. Resolve api_key — use slot-specific CredentialManager entry
        api_key = (
            self.cred_manager.get_credential(provider)               # CredentialManager (multi-key)
            or os.getenv(f"{env_prefix}API_KEY", "not-needed")       # single-key env fallback
        )


        logger.info(f"  base_url={base_url} | api_key={'set' if api_key and api_key != 'not-needed' else 'not-needed'}")

        return self.get_openai_compatible_model(
            base_url=base_url,
            api_key=api_key,
            model_name=model_name,
            temperature=temperature,
            **kwargs,
        )
