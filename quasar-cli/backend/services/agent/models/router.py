"""
Model Router for AI Agent

Routes requests to the appropriate model based on:
- Task type
- Provider availability
- Fallback chain

Configurable via config.py - easy to add new models.
"""

from typing import Optional, Any, List, Dict
from .providers import ModelProviders
from .credentials import CredentialManager
from ..config import AgentConfig
import logging

# Setup logger
logger = logging.getLogger("router")


class ModelRouter:
    """
    Routes requests to appropriate models with fallback support.
    
    Uses AgentConfig for task-to-model mapping.
    Automatically falls back when provider unavailable.
    """
    
    def __init__(self):
        self.providers = ModelProviders()
        self.cred_manager = CredentialManager()
        
        logger.debug("ModelRouter initialized")
    
    def get_model(
        self,
        task_type: str,
        fallback_level: int = 0,
        temperature: float = None,
        **kwargs
    ) -> Optional[Any]:
        """
        Get appropriate model for a task type.
        
        Args:
            task_type: Type of task (e.g., "chat", "code_generation")
            fallback_level: Which fallback to use (0 = primary)
            temperature: Override default temperature
            
        Returns:
            LangChain ChatModel instance or None
        """
        # Get model chain for this task
        models = AgentConfig.get_models_for_task(task_type)
        
        logger.info(f"🔍 get_model called: task={task_type}, fallback_level={fallback_level}, chain_length={len(models)}")
        
        if fallback_level >= len(models):
            # No more fallbacks available
            logger.warning(f"❌ No more fallback models available for task '{task_type}' at level {fallback_level}")
            return None
        
        provider, model_key = models[fallback_level]
        logger.info(f"  📌 Trying provider={provider}, model_key={model_key}")
        
        # Check if provider is available
        if not self.cred_manager.is_provider_available(provider):
            logger.warning(f"  ⚠️ Provider {provider} not available, trying next fallback...")
            return self.get_model(task_type, fallback_level + 1, temperature, **kwargs)
        
        logger.debug(f"  ✅ Provider {provider} is available")

        # Resolve model name — look up config first, fall back to using key as-is.
        # This supports providers with no pre-registered models (e.g. 'custom')
        # where the model_key IS the model name (e.g. "gpt-4o-mini", "qwen-3-235b").
        provider_config = AgentConfig.get_provider(provider)
        if provider_config and model_key in provider_config.models:
            model_config = provider_config.models[model_key]
            actual_model_name = model_config.name
            actual_temperature = temperature or model_config.temperature
        else:
            # Pass-through: model_key used as the model name directly
            actual_model_name = model_key
            actual_temperature = temperature or 0.7
            logger.info(f"  ℹ️ Model '{model_key}' not in {provider} config — using as model name directly")

        logger.info(f"  🎯 Creating model: {provider}/{actual_model_name}")

        # Create model instance
        model = self.providers.get_model(
            provider=provider,
            model_name=actual_model_name,
            temperature=actual_temperature,
            **kwargs
        )

        if model is None:
            logger.warning(f"  ❌ Model creation FAILED for {provider}/{actual_model_name}, trying next fallback...")
            return self.get_model(task_type, fallback_level + 1, temperature, **kwargs)

        logger.info(f"  ✅ Model created successfully: {provider}/{actual_model_name}")
        return model
    
    def get_model_for_provider(
        self,
        provider: str,
        model_name_or_key: str = None,
        temperature: float = 0.7,
        **kwargs
    ) -> Optional[Any]:
        """
        Get a specific model from a specific provider.
        
        Args:
            provider: Provider name (e.g., 'openai', 'anthropic', 'ollama')
            model_name_or_key: Model name OR config key (e.g., "zai-glm-4.7")
            temperature: Sampling temperature
            
        Returns:
            LangChain ChatModel instance or None
        """
        provider_config = AgentConfig.get_provider(provider)
        if not provider_config:
            logger.error(f"Provider '{provider}' not found in config")
            return None
        
        # If no model specified, use first model from provider config OR model_name_or_key as-is
        if not model_name_or_key:
            if not provider_config.models:
                logger.error(f"No model name provided and no models configured for provider '{provider}'")
                return None
            # Get first model key from config
            first_model_key = list(provider_config.models.keys())[0]
            model_name_or_key = first_model_key
            logger.debug(f"No model specified, using first model: {first_model_key}")
        
        # Check if model_name_or_key is a config key
        if model_name_or_key in provider_config.models:
            actual_model = provider_config.models[model_name_or_key]
            model_name = actual_model.name
            logger.debug(f"Resolved config key '{model_name_or_key}' -> model '{model_name}'")
        else:
            # Assume it's already a model name
            model_name = model_name_or_key
        
        return self.providers.get_model(
            provider=provider,
            model_name=model_name,
            temperature=temperature,
            **kwargs
        )
    
    def get_available_providers(self) -> List[str]:
        """Get list of providers with available credentials (dynamic, not hardcoded)."""
        available = []
        for provider in AgentConfig.PROVIDERS:
            if self.cred_manager.is_provider_available(provider):
                available.append(provider)
        return available
    
    async def invoke_with_fallback(
        self,
        task_type: str,
        messages: List[Any],
        temperature: float = None,
        **kwargs
    ) -> tuple[Optional[Any], str, str]:
        """
        Invoke model with automatic fallback on failure.
        
        Args:
            task_type: Task type for model selection
            messages: LangChain messages
            temperature: Override temperature
            
        Returns:
            Tuple of (response, provider_used, model_used) or (None, "", "")
        """
        models = AgentConfig.get_models_for_task(task_type)
        logger.info(f"🔄 invoke_with_fallback: task={task_type}, {len(models)} models in chain")
        
        for fallback_level, (provider, model_key) in enumerate(models):
            logger.info(f"  Trying fallback {fallback_level}: {provider}/{model_key}")
            model = self.get_model(task_type, fallback_level, temperature, **kwargs)
            if model is None:
                logger.warning(f"  ⚠️ Model creation failed for {provider}/{model_key}")
                continue
                
            try:
                logger.debug(f"  Invoking {provider}/{model_key}...")
                response = await model.ainvoke(messages)
                # Get model name
                provider_config = AgentConfig.get_provider(provider)
                model_name = provider_config.models[model_key].name if provider_config else "unknown"
                logger.info(f"  ✅ Success: {provider}/{model_name}")
                return (response, provider, model_name)
            except Exception as e:
                logger.warning(f"  ❌ Failed ({provider}/{model_key}): {e}")
                # Rotate credential and try next
                self.cred_manager.rotate_credential(provider)
                continue
        
        # All models in chain failed
        logger.error(f"❌ All models failed for task '{task_type}'")
        return (None, "", "")
