"""Authenticated HTTP views for serving Reolink recording assets."""
from __future__ import annotations

import logging
import mimetypes
import os
from pathlib import Path

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import DATA_COORDINATOR, DOMAIN

_LOGGER = logging.getLogger(__name__)

_HTTP_VIEW_REGISTERED = False


def _safe_filename(filename: str) -> str | None:
    """Return filename if it is a bare basename with no path components."""
    if not filename or filename != os.path.basename(filename):
        return None
    if filename in {".", ".."} or "/" in filename or "\\" in filename:
        return None
    return filename


def _resolve_recording_path(hass: HomeAssistant, filename: str) -> Path | None:
    """Locate a recording/snapshot file by basename across loaded coordinators."""
    for key, entry_data in hass.data.get(DOMAIN, {}).items():
        if key.startswith("_") or not isinstance(entry_data, dict):
            continue
        coordinator = entry_data.get(DATA_COORDINATOR)
        if coordinator is None:
            continue

        for path_map in (
            coordinator.recording_paths,
            getattr(coordinator, "snapshot_paths", {}),
            getattr(coordinator, "jpg_snapshot_paths", {}),
        ):
            for path_str in path_map.values():
                path = Path(path_str)
                if path.name == filename and path.is_file():
                    return path

        # Fallback: look directly in the recordings directory
        candidate = Path(coordinator.recordings_dir) / filename
        if candidate.is_file():
            return candidate

    return None


class ReolinkRecordingsMediaView(HomeAssistantView):
    """Serve recording MP4/GIF/JPG files to authenticated users."""

    url = "/api/reolink_recordings/{filename}"
    name = "api:reolink_recordings:media"
    requires_auth = True

    async def get(self, request: web.Request, filename: str) -> web.StreamResponse:
        """Return the requested recording asset."""
        safe_name = _safe_filename(filename)
        if safe_name is None:
            raise web.HTTPBadRequest(text="Invalid filename")

        hass: HomeAssistant = request.app["hass"]
        path = await hass.async_add_executor_job(
            _resolve_recording_path, hass, safe_name
        )
        if path is None:
            raise web.HTTPNotFound(text="File not found")

        mime_type, _ = mimetypes.guess_type(str(path))
        _LOGGER.debug("Serving %s (%s)", path, mime_type)
        return web.FileResponse(
            path,
            headers={"Content-Type": mime_type or "application/octet-stream"},
        )


def async_setup_http(hass: HomeAssistant) -> None:
    """Register authenticated media views (idempotent)."""
    global _HTTP_VIEW_REGISTERED
    if _HTTP_VIEW_REGISTERED:
        return
    hass.http.register_view(ReolinkRecordingsMediaView())
    _HTTP_VIEW_REGISTERED = True
    # Clean up legacy flag that previously broke media browsing
    hass.data.setdefault(DOMAIN, {}).pop("_http_view_registered", None)
    _LOGGER.debug("Registered /api/reolink_recordings media view")
