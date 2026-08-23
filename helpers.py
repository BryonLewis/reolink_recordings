"""Shared helpers for the Reolink Recordings integration."""
from pathlib import Path

from homeassistant.core import HomeAssistant


def resolve_storage_path(hass: HomeAssistant, storage_path: str) -> Path:
    """Resolve storage_path to an absolute Path.

    Absolute paths are used as-is. Relative paths are resolved under the
    Home Assistant config directory.
    """
    path = Path(storage_path.strip())
    if path.is_absolute():
        return path
    return Path(hass.config.path(storage_path))


def is_www_storage_path(hass: HomeAssistant, storage_path: str) -> bool:
    """Return True if storage_path is under the publicly served www/ tree."""
    normalized = str(storage_path).replace("\\", "/").strip().lstrip("./")
    if normalized == "www" or normalized.startswith("www/"):
        return True

    try:
        resolved = resolve_storage_path(hass, storage_path).resolve()
        www_root = Path(hass.config.path("www")).resolve()
        resolved.relative_to(www_root)
        return True
    except (ValueError, OSError):
        return False


def validate_storage_path(hass: HomeAssistant, storage_path: str) -> str | None:
    """Validate storage_path; return an error key or None if valid.

    Absolute paths are allowed (e.g. /media or a NAS mount). Relative paths
    must stay under the Home Assistant config directory (no ``..`` escape).
    Paths under www/ are allowed but insecure — callers should warn the user.
    """
    if not storage_path or not str(storage_path).strip():
        return "invalid_storage_path"

    path = Path(storage_path.strip())
    if ".." in path.parts:
        return "invalid_storage_path"

    if path.is_absolute():
        return None

    # Relative path: must resolve under config root (blocks .. and similar).
    config_root = Path(hass.config.path()).resolve()
    try:
        resolve_storage_path(hass, storage_path).resolve().relative_to(config_root)
    except (ValueError, OSError):
        return "invalid_storage_path"

    return None
