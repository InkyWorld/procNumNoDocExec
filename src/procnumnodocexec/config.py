from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import cast

from decouple import AutoConfig  # type: ignore[import]

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_config = AutoConfig(search_path=PROJECT_ROOT)


def _get_str(key: str, default: str) -> str:
    """Read a string setting with default fallback."""

    return cast(str, _config(key, default=default, cast=str))


@dataclass(frozen=True)
class SettingsDB:
    server: str
    database: str
    user: str
    password: str
    port: str = "5432"


@lru_cache(maxsize=1)
def get_db_settings() -> SettingsDB:
    """Return cached settings loaded from the environment/.env."""
    return SettingsDB(
        server=_get_str("DB_SERVER", ""),
        database=_get_str("DB_NAME", ""),
        user=_get_str("DB_USER", ""),
        password=_get_str("DB_PASSWORD", ""),
        port=_get_str("DB_PORT", "5432"),
    )


@dataclass(frozen=True)
class SettingsSMB:
    server: str
    share: str
    username: str
    password: str
    domain: str = ""
    folder_path: str = ""


@lru_cache(maxsize=1)
def get_smb_settings() -> SettingsSMB:
    """Return cached settings loaded from the environment/.env."""
    return SettingsSMB(
        server=_get_str("SMB_SERVER", ""),
        share=_get_str("SMB_SHARE", ""),
        username=_get_str("SMB_USERNAME", ""),
        password=_get_str("SMB_PASSWORD", ""),
        domain=_get_str("SMB_DOMAIN", ""),
    )


@dataclass(frozen=True)
class SettingsAzure:
    endpoint: str
    api_version: str = "2025-04-01-preview"
    model: str = "gpt-4.1-mini"
    api_key: str = ""


@lru_cache(maxsize=1)
def get_azure_settings() -> SettingsAzure:
    """Return cached Azure OpenAI settings loaded from the environment/.env."""
    return SettingsAzure(
        endpoint=_get_str("AZURE_OPENAI_ENDPOINT", ""),
        api_version=_get_str("AZURE_OPENAI_API_VERSION", "2025-04-01-preview"),
        model=_get_str("AZURE_MODEL", "gpt-4.1-mini"),
        api_key=_get_str("AZURE_API_KEY", ""),
    )


__all__ = [
    "SettingsDB",
    "get_db_settings",
    "get_smb_settings",
    "SettingsAzure",
    "get_azure_settings",
]
