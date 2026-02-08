"""
LangChain Model Providers

Factory functions to create LangChain ChatModel instances for:
- Cerebras (via OpenAI-compatible API)
- Groq
- Cloudflare (via OpenAI-compatible API) 
- Ollama (local)

Easy to add new providers or models.
"""

from typing import Optional, Any
from .credentials import CredentialManager
import logging

# Setup logger
logger = logging.getLogger("providers")


class ModelProviders:
    """
    Factory for creating LangChain model instances.
    
    All methods return LangChain ChatModel instances.
    Lazy import to avoid loading unused providers.
    """
    
    def __init__(self):
        self.cred_manager = CredentialManager()
        logger.debug("ModelProviders initialized")
    
    def get_ollama_model(
        self, 
        model_name: str = "qwen2.5-coder:7b",
        temperature: float = 0.7,
        **kwargs
    ) -> Optional[Any]:
        """
        Get Ollama model (local).
        
        Args:
            model_name: Model name (e.g., "qwen2.5-coder:7b")
            temperature: Sampling temperature
            
        Returns:
            ChatOllama instance or None
        """
        logger.info(f"🦙 Creating Ollama model: {model_name}")
        try:
            from langchain_ollama import ChatOllama
            
            # Use custom URL if provided, otherwise default to local
            base_url = self.cred_manager.get_setting("ollama_url", "http://localhost:11434")
            
            model = ChatOllama(
                model=model_name,
                base_url=base_url,
                temperature=temperature,
                **kwargs
            )
            logger.info(f"✅ Ollama model created at {base_url}: {model_name}")
            return model
        except ImportError:
            logger.error("❌ langchain-ollama not installed")
            return None
        except Exception as e:
            logger.error(f"❌ Error creating Ollama model: {e}")
            return None
    
    def get_cerebras_model(
        self,
        model_name: str = "qwen-3-32b",
        temperature: float = 0.7,
        **kwargs
    ) -> Optional[Any]:
        """
        Get Cerebras model via OpenAI-compatible API.
        
        Args:
            model_name: Model name (e.g., "qwen-3-32b", "zai-glm-4.7")
            temperature: Sampling temperature
            
        Returns:
            ChatOpenAI instance or None
        """
        logger.info(f"🧠 Creating Cerebras model: {model_name}")
        api_key = self.cred_manager.get_credential("cerebras")
        if not api_key:
            logger.warning("❌ No Cerebras API key available")
            return None
            
        try:
            from langchain_openai import ChatOpenAI
            
            model = ChatOpenAI(
                base_url="https://api.cerebras.ai/v1",
                api_key=api_key,
                model=model_name,
                temperature=temperature,
                **kwargs
            )
            logger.info(f"✅ Cerebras model created: {model_name}")
            return model
        except ImportError:
            logger.error("❌ langchain-openai not installed")
            return None
        except Exception as e:
            logger.error(f"❌ Error creating Cerebras model: {e}")
            return None
    
    def get_groq_model(
        self,
        model_name: str = "llama-3.3-70b-versatile",
        temperature: float = 0.7,
        **kwargs
    ) -> Optional[Any]:
        """
        Get Groq model.
        
        Args:
            model_name: Model name (e.g., "llama-3.3-70b-versatile")
            temperature: Sampling temperature
            
        Returns:
            ChatGroq instance or None
        """
        logger.info(f"💙 Creating Groq model: {model_name}")
        api_key = self.cred_manager.get_credential("groq")
        if not api_key:
            logger.warning("❌ No Groq API key available")
            return None
            
        try:
            from langchain_groq import ChatGroq
            
            model = ChatGroq(
                model=model_name,
                groq_api_key=api_key,
                temperature=temperature,
                **kwargs
            )
            logger.info(f"✅ Groq model created: {model_name}")
            return model
        except ImportError:
            logger.error("❌ langchain-groq not installed")
            return None
        except Exception as e:
            logger.error(f"❌ Error creating Groq model: {e}")
            return None
    
    def get_cloudflare_model(
        self,
        model_name: str = "@cf/meta/llama-3.1-70b-instruct",
        temperature: float = 0.7,
        **kwargs
    ) -> Optional[Any]:
        """
        Get Cloudflare model via OpenAI-compatible API.
        
        Args:
            model_name: Model name (e.g., "@cf/meta/llama-3.1-70b-instruct")
            temperature: Sampling temperature
            
        Returns:
            ChatOpenAI instance or None
        """
        logger.info(f"☁️ Creating Cloudflare model: {model_name}")
        creds = self.cred_manager.get_cloudflare_credentials()
        if not creds:
            logger.warning("❌ No Cloudflare credentials available")
            return None
            
        account_id, api_token = creds
        
        try:
            from langchain_openai import ChatOpenAI
            
            model = ChatOpenAI(
                base_url=f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1",
                api_key=api_token,
                model=model_name,
                temperature=temperature,
                **kwargs
            )
            logger.info(f"✅ Cloudflare model created: {model_name}")
            return model
        except ImportError:
            logger.error("❌ langchain-openai not installed")
            return None
        except Exception as e:
            logger.error(f"❌ Error creating Cloudflare model: {e}")
            return None
    
    def get_model(
        self,
        provider: str,
        model_name: str,
        temperature: float = 0.7,
        **kwargs
    ) -> Optional[Any]:
        """
        Generic method to get model by provider name.
        
        Args:
            provider: Provider name (ollama, cerebras, groq, cloudflare)
            model_name: Model name
            temperature: Sampling temperature
            
        Returns:
            ChatModel instance or None
        """
        logger.info(f"🔧 get_model called: provider={provider}, model={model_name}")
        
        if provider == "ollama":
            return self.get_ollama_model(model_name, temperature, **kwargs)
        elif provider == "cerebras":
            return self.get_cerebras_model(model_name, temperature, **kwargs)
        elif provider == "groq":
            return self.get_groq_model(model_name, temperature, **kwargs)
        elif provider == "cloudflare":
            return self.get_cloudflare_model(model_name, temperature, **kwargs)
        else:
            logger.error(f"❌ Unknown provider: {provider}")
            return None
