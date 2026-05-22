"""Azure Key Vault integration for secure secret management.

Falls back to environment variables when Key Vault is not configured.
Mirrors the get_secret() pattern used in Open WebUI.
"""
import os
import logging
from functools import lru_cache

log = logging.getLogger(__name__)

_secret_client = None
_vault_enabled = False

try:
    from azure.identity import DefaultAzureCredential
    from azure.keyvault.secrets import SecretClient

    vault_host = os.environ.get("VAULT_HOST", None)
    if vault_host:
        vault_url = f"https://{vault_host}.vault.azure.net/"
        _secret_client = SecretClient(
            vault_url=vault_url, credential=DefaultAzureCredential()
        )
        _vault_enabled = True
        log.info(f"Azure Key Vault enabled: {vault_url}")
    else:
        log.info("VAULT_HOST not set. Using environment variables only.")
except ImportError:
    log.info(
        "Azure Key Vault libraries not installed. Using environment variables only."
    )
except Exception as e:
    log.warning(
        f"Failed to initialize Azure Key Vault: {e}. Falling back to environment variables."
    )


@lru_cache(maxsize=256)
def get_secret(key: str, default: str = "") -> str:
    """Retrieve a secret from Azure Key Vault or environment variables.

    Priority:
    1. Azure Key Vault (if enabled and secret exists)
    2. Environment variable
    3. Default value

    Args:
        key: The secret/environment variable name
        default: Default value if not found

    Returns:
        The secret value
    """
    if _vault_enabled and _secret_client:
        try:
            vault_key = key.replace("_", "-")
            secret = _secret_client.get_secret(vault_key)
            log.debug(f"Retrieved '{key}' from Azure Key Vault")
            return secret.value
        except Exception as e:
            log.debug(f"Secret '{key}' not in Key Vault, checking environment: {e}")

    value = os.environ.get(key, default)
    if value != default:
        log.debug(f"Retrieved '{key}' from environment variable")

    return value


def clear_secret_cache():
    """Clear the secret cache. Useful for testing or forcing refresh."""
    get_secret.cache_clear()
