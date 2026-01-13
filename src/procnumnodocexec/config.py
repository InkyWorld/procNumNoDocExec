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
    driver: str = "ODBC Driver 18 for SQL Server"
    trust_cert: str = "yes"


@lru_cache(maxsize=1)
def get_db_settings() -> SettingsDB:
    """Return cached settings loaded from the environment/.env."""
    return SettingsDB(
        server=_get_str("DB_SERVER", ""),
        database=_get_str("DB_NAME", ""),
        user=_get_str("DB_USER", ""),
        password=_get_str("DB_PASSWORD", ""),
        driver=_get_str("DB_DRIVER", "ODBC Driver 18 for SQL Server"),
        trust_cert=_get_str("DB_TRUST_CERT", "yes"),
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

__all__ = ["SettingsDB", "get_db_settings", "get_smb_settings"]