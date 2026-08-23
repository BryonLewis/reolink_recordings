"""Frontend code for Reolink Recordings component."""
from __future__ import annotations

import concurrent.futures
import json
import logging
from pathlib import Path
import shutil

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

CARD_FILES = (
    "reolink-recording-card.js",
    "reolink-summary-card.js",
)


def _integration_version(component_dir: Path) -> str:
    """Read version from manifest.json for cache-busting."""
    try:
        manifest = json.loads((component_dir / "manifest.json").read_text(encoding="utf-8"))
        return str(manifest.get("version") or "0")
    except (OSError, ValueError, TypeError):
        return "0"


def _sync_card_to_www(component_dir: Path, www_dir: Path, filename: str) -> bool:
    """Copy a frontend card into www/ when missing or stale."""
    src = component_dir / "frontend" / filename
    dest = www_dir / filename
    if not src.exists():
        _LOGGER.error("Card JS file not found at %s", src)
        return False
    try:
        www_dir.mkdir(parents=True, exist_ok=True)
        needs_copy = (
            not dest.exists()
            or src.stat().st_mtime > dest.stat().st_mtime
            or src.stat().st_size != dest.stat().st_size
        )
        if needs_copy:
            shutil.copy2(src, dest)
            _LOGGER.info("Updated %s in www directory", filename)
        return True
    except OSError as err:
        _LOGGER.error("Failed to copy %s to www directory: %s", filename, err)
        return False


def setup_frontend(hass: HomeAssistant) -> None:
    """Ensure Lovelace card JS files are present under www/.

    Cards are loaded via Dashboard → Resources (versioned URLs). We intentionally
    do **not** call ``add_extra_js_url`` here: an unversioned extra URL would load
    first and permanently register a stale custom element, so later cache-busted
    resource loads cannot replace it.
    """
    component_dir = Path(__file__).parent
    www_dir = Path(hass.config.path("www"))
    version = _integration_version(component_dir)

    def copy_all() -> None:
        for filename in CARD_FILES:
            _sync_card_to_www(component_dir, www_dir, filename)

    with concurrent.futures.ThreadPoolExecutor() as executor:
        executor.submit(copy_all).result()

    _LOGGER.debug(
        "Reolink frontend cards synced to www/ (v%s). "
        "Load them via Lovelace resources, e.g. /local/reolink-summary-card.js?v=%s",
        version,
        version,
    )
