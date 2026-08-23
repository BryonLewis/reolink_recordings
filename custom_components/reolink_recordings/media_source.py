"""Media source implementation for Reolink Recordings."""
from __future__ import annotations

import logging
import mimetypes
import os

from homeassistant.components.media_player.const import MediaClass, MediaType
from homeassistant.components.media_source.error import MediaSourceError, Unresolvable
from homeassistant.components.media_source.models import (
    BrowseMediaSource,
    MediaSource,
    MediaSourceItem,
    PlayMedia,
)
from homeassistant.core import HomeAssistant

from .const import DATA_COORDINATOR, DOMAIN

_LOGGER = logging.getLogger(__name__)

MEDIA_CLASS_DIRECTORY = getattr(MediaClass, "DIRECTORY", "directory")
MEDIA_CLASS_VIDEO = getattr(MediaClass, "VIDEO", "video")
MEDIA_TYPE_VIDEO = getattr(MediaType, "VIDEO", "video")


def _iter_coordinators(hass: HomeAssistant):
    """Yield loaded entry coordinators (skip internal DOMAIN keys)."""
    for _key, entry_data in hass.data.get(DOMAIN, {}).items():
        if not isinstance(entry_data, dict):
            continue
        coordinator = entry_data.get(DATA_COORDINATOR)
        if coordinator is not None:
            yield coordinator


def _api_media_url(filename: str) -> str:
    """Return the authenticated HTTP API path for a recording asset."""
    return f"/api/{DOMAIN}/{filename}"


async def async_get_media_source(hass: HomeAssistant) -> MediaSource:
    """Set up Reolink Recordings media source."""
    return ReolinkRecordingsMediaSource(hass)


class ReolinkRecordingsMediaSource(MediaSource):
    """Provide Reolink recordings as media sources."""

    name: str = "Reolink Recordings"

    def __init__(self, hass: HomeAssistant):
        """Initialize Reolink Recordings source."""
        super().__init__(DOMAIN)
        self.hass = hass

    def _find_path(self, filename: str) -> str | None:
        """Find a recording/snapshot filesystem path by basename."""
        for coordinator in _iter_coordinators(self.hass):
            for path_map in (
                coordinator.recording_paths,
                getattr(coordinator, "snapshot_paths", {}),
                getattr(coordinator, "jpg_snapshot_paths", {}),
            ):
                for path_str in path_map.values():
                    if os.path.basename(path_str) == filename:
                        return path_str
        return None

    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        """Resolve a media item to a playable URL."""
        if not item.identifier:
            raise Unresolvable("Media item is not a file")

        if not any(_iter_coordinators(self.hass)):
            raise Unresolvable("No Reolink Recordings instances configured")

        path = self._find_path(item.identifier)
        if path is None:
            raise Unresolvable(f"Could not find file: {item.identifier}")

        mime_type, _ = mimetypes.guess_type(path)
        # Serve via the authenticated API view (works outside www/)
        return PlayMedia(
            _api_media_url(item.identifier),
            mime_type or "application/octet-stream",
        )

    async def async_browse_media(self, item: MediaSourceItem) -> BrowseMediaSource:
        """Browse media."""
        if not any(_iter_coordinators(self.hass)):
            return BrowseMediaSource(
                domain=DOMAIN,
                identifier=None,
                media_class=MEDIA_CLASS_DIRECTORY,
                media_content_type="",
                title=self.name,
                can_play=False,
                can_expand=False,
                children_media_class=MEDIA_CLASS_VIDEO,
                children=[],
            )

        # Root level - show all cameras
        if not item.identifier:
            return await self._async_browse_cameras()

        raise MediaSourceError(f"Unknown identifier: {item.identifier}")

    async def _async_browse_cameras(self) -> BrowseMediaSource:
        """Browse cameras."""
        cameras: dict[str, str] = {}
        thumbnails: dict[str, str] = {}

        for coordinator in _iter_coordinators(self.hass):
            for camera_name, recording_path in coordinator.recording_paths.items():
                cameras[camera_name] = recording_path
                gif = getattr(coordinator, "snapshot_paths", {}).get(camera_name)
                jpg = getattr(coordinator, "jpg_snapshot_paths", {}).get(camera_name)
                if gif:
                    thumbnails[camera_name] = _api_media_url(os.path.basename(gif))
                elif jpg:
                    thumbnails[camera_name] = _api_media_url(os.path.basename(jpg))

        media_sources = []
        for camera_name, recording_path in cameras.items():
            filename = os.path.basename(recording_path)
            media_sources.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=filename,
                    media_class=MEDIA_CLASS_VIDEO,
                    media_content_type=MEDIA_TYPE_VIDEO,
                    title=camera_name,
                    can_play=True,
                    can_expand=False,
                    thumbnail=thumbnails.get(camera_name),
                )
            )

        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=None,
            media_class=MEDIA_CLASS_DIRECTORY,
            media_content_type="",
            title=self.name,
            can_play=False,
            can_expand=True,
            children_media_class=MEDIA_CLASS_VIDEO,
            children=sorted(media_sources, key=lambda x: x.title),
        )
