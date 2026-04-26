"""
Credential Manager for AI Agent

Handles:
- Loading credentials from .env
- Multi-credential support (2 keys per provider)
- Round-robin rotation when rate limited
- Easy to add new providers
"""

import os
import json
from typing import Dict, Optional, Any, List
from dataclasses import dataclass
from dotenv import load_dotenv
import logging
from contextvars import ContextVar

# Setup logger
logger = logging.getLogger("credentials")

# Load environment variables
load_dotenv()

# Request-scoped user credentials
# Maps provider name -> ProviderCredentials instance
user_credentials_context: ContextVar[Dict[str, Any]] = ContextVar("user_credentials", default={})

# Request-scoped user settings (e.g., Ollama URL)
user_settings_context: ContextVar[Dict[str, Any]] = ContextVar("user_settings", default={})


@dataclass
class Credential:
    """Single credential entry."""
    key: str
    is_active: bool = True
    # Note: Real quota tracking would require API calls to each provider
    # Not implemented - would add latency and complexity
    

@dataclass 
class ProviderCredentials:
    """Credentials for a provider (supports multiple keys)."""
    current_index: int = 0
    credentials: list = None
    
    def __post_init__(self):
        if self.credentials is None:
            self.credentials = []


class CredentialManager:
    """
    Manages API credentials for all providers.
    
    Features:
    - Load from .env file
    - Multiple keys per provider (for higher rate limits)
    - Round-robin rotation
    - Fallback to next credential when rate limited
    - Request-scoped user override via contextvars
    """
    
    _instance = None
    
    def __new__(cls):
        """Singleton pattern - only one instance needed."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._initialized = True
        self._providers: Dict[str, ProviderCredentials] = {}
        self._load_credentials()
    
    @staticmethod
    def set_user_keys(provider_keys: Dict[str, List[str]], settings: Dict[str, Any] = None):
        """Set user keys and settings for the current request context."""
        ctx_creds = {}
        for provider, keys in provider_keys.items():
            if keys:
                creds = [Credential(key=k) for k in keys if k]
                if creds:
                    ctx_creds[provider] = ProviderCredentials(credentials=creds)
        
        user_credentials_context.set(ctx_creds)
        user_settings_context.set(settings or {})
        
        if ctx_creds or settings:
            logger.info(f"🔑 User context set (providers: {list(ctx_creds.keys())}, settings: {list((settings or {}).keys())})")

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a setting from user context or default."""
        settings = user_settings_context.get()
        return settings.get(key, default)
    
    def _load_credentials(self):
        """
        Load credentials from environment variables.

        Providers:
          ollama    — no key needed (URL-based auth)
          custom_1  — reads CUSTOM_1_API_KEY_1 / CUSTOM_1_API_KEY_2 (+ plain CUSTOM_1_API_KEY)
          custom_2  — reads CUSTOM_2_API_KEY_1 / CUSTOM_2_API_KEY_2
          custom_3  — reads CUSTOM_3_API_KEY_1 / CUSTOM_3_API_KEY_2
          custom_4  — reads CUSTOM_4_API_KEY_1 / CUSTOM_4_API_KEY_2
        """
        logger.info("🔑 Loading credentials from .env...")

        # Ollama — no credentials needed (URL handles auth for cloud tags)
        self._providers["ollama"] = ProviderCredentials(
            credentials=[Credential(key="local")]
        )

        # Custom slots 1–4 — each is a fully independent provider
        for n in [1, 2, 3, 4]:
            provider_name = f"custom_{n}"
            prefix = f"CUSTOM_{n}_"
            slot_creds = ProviderCredentials()

            # Numbered rotation keys: CUSTOM_N_API_KEY_1, CUSTOM_N_API_KEY_2
            for i in [1, 2, 3, 4]:
                key = os.getenv(f"{prefix}API_KEY_{i}")
                if key:
                    slot_creds.credentials.append(Credential(key=key))

            # Plain CUSTOM_N_API_KEY as single-key shorthand
            if not slot_creds.credentials:
                single = os.getenv(f"{prefix}API_KEY")
                if single:
                    slot_creds.credentials.append(Credential(key=single))

            self._providers[provider_name] = slot_creds
            logger.info(f"  {provider_name}: {len(slot_creds.credentials)} key(s) loaded")

    
    def get_key_count(self, provider: str) -> int:
        """Get number of active keys for a provider."""
        provider_creds = self._get_provider_creds(provider)
        if not provider_creds or not provider_creds.credentials:
            return 0
        return sum(1 for c in provider_creds.credentials if c.is_active)
    
    def get_total_key_count(self) -> int:
        """Get total number of keys across all loaded providers (for retry calculation)."""
        total = sum(
            self.get_key_count(prov)
            for prov in self._providers
            if prov != "ollama"  # Ollama uses a synthetic key, don't count it
        )
        logger.info(f"📊 Total API keys available: {total}")
        return total
    
    def _get_provider_creds(self, provider: str) -> Optional[ProviderCredentials]:
        """Get provider credentials, checking user context first."""
        user_creds = user_credentials_context.get()
        if provider in user_creds:
            return user_creds[provider]
        return self._providers.get(provider)

    def get_credential(self, provider: str) -> Optional[str]:
        """
        Get current credential for a provider.
        
        Returns:
            API key string, or None if no credentials available
        """
        provider_creds = self._get_provider_creds(provider)
        if not provider_creds or not provider_creds.credentials:
            return None
        
        current = provider_creds.current_index
        if current < len(provider_creds.credentials):
            cred = provider_creds.credentials[current]
            if b := cred.is_active:
                return cred.key
        
        return None
    

    def rotate_credential(self, provider: str) -> bool:
        """
        Rotate to next credential (when rate limited).
        
        Returns:
            True if successfully rotated, False if no more credentials
        """
        provider_creds = self._get_provider_creds(provider)
        if not provider_creds or not provider_creds.credentials:
            return False
        
        current = provider_creds.current_index
        total_creds = len(provider_creds.credentials)
        
        # If only one credential, can't rotate
        if total_creds <= 1:
            logger.warning(f"⚠️ Cannot rotate {provider}: only 1 credential available")
            return False
        
        # Try next credential (don't mark current as inactive yet - might be temporary)
        next_index = (current + 1) % total_creds
        
        # Check if we've tried all credentials already
        if next_index == current:
            logger.warning(f"⚠️ Cannot rotate {provider}: already at last credential")
            return False
        
        # Check if next credential is available
        if provider_creds.credentials[next_index].is_active:
            provider_creds.current_index = next_index
            logger.info(f"🔄 Rotated {provider} from key {current + 1} to key {next_index + 1}")
            return True
        
        # Next credential is inactive, try to find any active one
        for i in range(total_creds):
            if i != current and provider_creds.credentials[i].is_active:
                provider_creds.current_index = i
                logger.info(f"🔄 Rotated {provider} from key {current + 1} to key {i + 1}")
                return True
        
        logger.warning(f"⚠️ Cannot rotate {provider}: no active credentials remaining")
        return False
    
    def mark_credential_exhausted(self, provider: str) -> None:
        """
        Mark current credential as exhausted (inactive).
        Call this after confirming a credential is truly exhausted.
        
        Args:
            provider: Provider name
        """
        provider_creds = self._get_provider_creds(provider)
        if not provider_creds:
            return
        
        current = provider_creds.current_index
        if current < len(provider_creds.credentials):
            provider_creds.credentials[current].is_active = False
            logger.info(f"❌ Marked {provider} key {current + 1} as exhausted")
    
    def get_remaining_keys(self, provider: str) -> int:
        """
        Get count of remaining active keys for a provider.
        
        Args:
            provider: Provider name
            
        Returns:
            Number of active credentials remaining
        """
        provider_creds = self._get_provider_creds(provider)
        if not provider_creds:
            return 0
        
        return sum(1 for c in provider_creds.credentials if c.is_active)
    
    def is_provider_available(self, provider: str) -> bool:
        """Check if provider has available credentials / is usable."""
        import os
        if provider == "ollama":
            return True  # Ollama always reachable (local or cloud via URL)

        if provider.startswith("custom"):
            # Slot is available only if its CUSTOM_N_BASE_URL is configured.
            # Derive the env var name: custom_1 -> CUSTOM_1_BASE_URL
            slot = provider.split("_", 1)[1] if "_" in provider else ""
            env_key = f"CUSTOM_{slot.upper()}_BASE_URL" if slot else "CUSTOM_BASE_URL"
            return bool(os.getenv(env_key, "").strip())

        provider_creds = self._get_provider_creds(provider)
        if not provider_creds or not provider_creds.credentials:
            return False

        return any(c.is_active for c in provider_creds.credentials)
    
    def get_status(self) -> Dict[str, Any]:
        """Get status of all credentials (for health check)."""
        status = {}
        # Status shows system status, but mentions if user keys are active
        user_creds = user_credentials_context.get()
        
        for name, provider_creds in self._providers.items():
            total = len(provider_creds.credentials)
            active = sum(1 for c in provider_creds.credentials if c.is_active)
            
            # Check user override
            has_user_override = name in user_creds
            if has_user_override:
                u_total = len(user_creds[name].credentials)
                u_active = sum(1 for c in user_creds[name].credentials if c.is_active)
                total = u_total
                active = u_active

            status[name] = {
                "available": active > 0,
                "total_keys": total,
                "active_keys": active,
                "has_credentials": total > 0,
                "is_user_provided": has_user_override
            }
        return status
    
    def reset_credentials(self):
        """Reset all credentials to active (for daily reset)."""
        for provider_creds in self._providers.values():
            for cred in provider_creds.credentials:
                cred.is_active = True
