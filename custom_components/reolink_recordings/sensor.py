"""Sensor platform for Reolink Recordings."""
from datetime import UTC, datetime, timedelta
import logging
import os
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

from .const import (
    CONF_SNAPSHOT_FORMAT,
    DATA_COORDINATOR,
    DEFAULT_SNAPSHOT_FORMAT,
    DOMAIN,
    SNAPSHOT_FORMAT_BOTH,
    SNAPSHOT_FORMAT_GIF,
    SNAPSHOT_FORMAT_JPG,
)
from .coordinator import ReolinkRecordingsCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Reolink Recording sensors."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA_COORDINATOR]

    # We already have fresh data from __init__.py, so no need to refresh again
    # await coordinator.async_request_refresh()

    entities = []
    # Add a sensor for each camera once data is available
    if coordinator.data and "cameras" in coordinator.data:
        # Deduplicate cameras by slug to avoid creating duplicate sensors
        seen_slugs = set()
        for camera_data in coordinator.data["cameras"]:
            camera_name = camera_data["camera"]
            if "error" not in camera_data:
                slug = camera_name.lower().replace(" ", "_")
                if slug not in seen_slugs:
                    seen_slugs.add(slug)
                    entities.append(
                        ReolinkRecordingSensor(
                            coordinator,
                            camera_name,
                            config_entry.entry_id,
                        )
                    )
    
    async_add_entities(entities)


class ReolinkRecordingSensor(CoordinatorEntity, SensorEntity):
    """Sensor representing a Reolink camera recording."""

    def __init__(
        self,
        coordinator: ReolinkRecordingsCoordinator,
        camera_name: str,
        config_entry_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.camera_name = camera_name
        self._config_entry_id = config_entry_id
        self._camera_slug = camera_name.lower().replace(' ', '_')
        
        # Entity properties
        self._attr_name = f"{camera_name} Latest Recording"
        self._attr_unique_id = f"{DOMAIN}_{config_entry_id}_{self._camera_slug}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{config_entry_id}_{self._camera_slug}")},
            name=camera_name,
            manufacturer="Reolink",
            model="Camera",
            via_device=(DOMAIN, config_entry_id),  # This now references the parent device created in __init__.py
        )
        self._attr_icon = "mdi:video"
        
        # Fixed filenames for latest assets
        self._video_filename = f"{self._camera_slug}_latest.mp4"
        self._gif_snapshot_filename = f"{self._camera_slug}_latest.gif"
        self._jpg_snapshot_filename = f"{self._camera_slug}_latest.jpg"
        
        # Get the snapshot format configuration
        self._snapshot_format = coordinator.entry.options.get(
            CONF_SNAPSHOT_FORMAT, DEFAULT_SNAPSHOT_FORMAT
        )

    def _media_source_url(self, filename: str, timestamp: str) -> str:
        """Return an authenticated media-source URL for a recording asset."""
        return f"/media-source/{DOMAIN}/{filename}?t={timestamp}"
    
    def _find_camera_data(self) -> dict[str, Any] | None:
        """Find the best matching camera data for this sensor.
        
        When multiple entries match by slug (e.g., 'first_landing' and 'First Landing'),
        prefer the one with proper-case name and most recent date.
        """
        matches = []
        for camera_data in self.coordinator.data.get("cameras", []):
            camera_name = camera_data.get("camera", "")
            if (camera_name == self.camera_name or \
               camera_name.lower() == self.camera_name.lower()) and "error" not in camera_data:
                matches.append(camera_data)
        
        if not matches:
            return None
        
        if len(matches) == 1:
            return matches[0]
        
        # Prefer proper-case name (contains space) over lowercase slug
        proper_case = [m for m in matches if " " in m.get("camera", "")]
        if proper_case:
            matches = proper_case
        
        # Among remaining matches, prefer the one with the most recent date
        def _sort_key(m):
            date_str = m.get("date", "0/0/0")
            try:
                parts = date_str.split("/")
                return (int(parts[0]), int(parts[1]), int(parts[2]))
            except (ValueError, IndexError):
                return (0, 0, 0)
        
        matches.sort(key=_sort_key, reverse=True)
        return matches[0]

    @property
    def available(self) -> bool:
        """Always available if we have a path for the latest recording."""
        if self.camera_name in self.coordinator.recording_paths:
            return True
        # Case-insensitive fallback
        return any(k.lower() == self.camera_name.lower() for k in self.coordinator.recording_paths)
    
    def _get_corrected_timestamp(self, camera_data: dict[str, Any]) -> tuple:
        """Return (date, timestamp) using file mtime if the API timestamp is stale.
        
        The Reolink NVR API can lag behind the actual recording file on disk.
        If the file mtime is more than 2 minutes newer than the API timestamp,
        we use the file mtime instead.
        """
        api_date = camera_data.get("date")
        api_timestamp = camera_data.get("timestamp")
        
        if not api_date or not api_timestamp:
            return (api_date or "Unknown", api_timestamp or "Unknown")
        
        # Get the file path - try exact match first, then case-insensitive
        recording_path = self.coordinator.recording_paths.get(self.camera_name)
        if not recording_path:
            for k, v in self.coordinator.recording_paths.items():
                if k.lower() == self.camera_name.lower():
                    recording_path = v
                    break
        
        if recording_path:
            try:
                # HA runs in UTC internally; convert file mtime to HA's configured
                # timezone (e.g. America/Edmonton) so the card's _parseRecordingDate
                # interprets it correctly as local time.
                tz_str = None
                if self.coordinator.hass and self.coordinator.hass.config:
                    tz_str = self.coordinator.hass.config.time_zone
                if not tz_str:
                    tz_str = "UTC"
                tz = ZoneInfo(tz_str)
                file_mtime = datetime.fromtimestamp(
                    os.path.getmtime(recording_path), tz=UTC
                ).astimezone(tz)
                date_parts = api_date.split("/")
                time_parts = api_timestamp.split(":")
                if len(date_parts) == 3 and len(time_parts) == 3:
                    api_dt = datetime(
                        int(date_parts[0]), int(date_parts[1]), int(date_parts[2]),
                        int(time_parts[0]), int(time_parts[1]), int(time_parts[2]),
                        tzinfo=tz
                    )
                    if file_mtime - api_dt > timedelta(minutes=2):
                        _LOGGER.debug(
                            "File mtime %s is newer than API timestamp %s for %s, using file mtime",
                            file_mtime.isoformat(), api_dt.isoformat(), self.camera_name
                        )
                        return (file_mtime.strftime("%Y/%m/%d"), file_mtime.strftime("%H:%M:%S"))
            except (OSError, ValueError, IndexError) as e:
                _LOGGER.debug("Could not compare file mtime for %s: %s", self.camera_name, e)
        
        return (api_date, api_timestamp)
    
    @property
    def state(self) -> str | None:
        """Return the state of the sensor."""
        camera_data = self._find_camera_data()
        if camera_data is None:
            return None
        
        date, timestamp = self._get_corrected_timestamp(camera_data)
        event_type = camera_data.get("event_type", "Unknown")
        return f"{date} {timestamp} - {event_type}"
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        attributes = {}
        now = datetime.now()
        timestamp = now.strftime("%s")  # Unix timestamp for cache busting
        
        # Find this camera's data using the same logic as state
        camera_data = self._find_camera_data()
        if camera_data is not None:
            # Use corrected timestamp (falls back to file mtime if API is stale)
            corr_date, corr_timestamp = self._get_corrected_timestamp(camera_data)
            attributes["date"] = corr_date
            attributes["timestamp"] = corr_timestamp
            attributes["duration"] = camera_data.get("duration")
            attributes["event_type"] = camera_data.get("event_type")
            attributes["last_updated"] = now.isoformat()
            
            # Get the file path - try exact match first, then case-insensitive
            recording_path = self.coordinator.recording_paths.get(self.camera_name)
            if not recording_path:
                for k, v in self.coordinator.recording_paths.items():
                    if k.lower() == self.camera_name.lower():
                        recording_path = v
                        break
            
            if recording_path:
                # Expose filename only — never the full filesystem path
                attributes["file_name"] = self._video_filename
                
                # Media URL (MP4) for tap-to-play via authenticated media source
                attributes["media_url"] = self._media_source_url(
                    self._video_filename, timestamp
                )

                # Select the appropriate snapshot image based on configuration
                # Lookup paths with case-insensitive fallback
                gif_path = getattr(self.coordinator, "snapshot_paths", {}).get(self.camera_name)
                if not gif_path:
                    for k, v in getattr(self.coordinator, "snapshot_paths", {}).items():
                        if k.lower() == self.camera_name.lower():
                            gif_path = v
                            break

                jpg_path = getattr(self.coordinator, "jpg_snapshot_paths", {}).get(self.camera_name)
                if not jpg_path:
                    for k, v in getattr(self.coordinator, "jpg_snapshot_paths", {}).items():
                        if k.lower() == self.camera_name.lower():
                            jpg_path = v
                            break
                
                # Choose which snapshot to use for entity_picture
                if self._snapshot_format == SNAPSHOT_FORMAT_GIF and gif_path:
                    # Use GIF if configured for GIF only
                    picture_url = self._media_source_url(
                        self._gif_snapshot_filename, timestamp
                    )
                    attributes["entity_picture"] = picture_url
                    self._attr_entity_picture = picture_url
                elif self._snapshot_format == SNAPSHOT_FORMAT_JPG and jpg_path:
                    # Use JPG if configured for JPG only
                    picture_url = self._media_source_url(
                        self._jpg_snapshot_filename, timestamp
                    )
                    attributes["entity_picture"] = picture_url
                    self._attr_entity_picture = picture_url
                elif self._snapshot_format == SNAPSHOT_FORMAT_BOTH:
                    # If both, prefer GIF for entity_picture but include JPG as alternate_picture
                    if gif_path:
                        gif_url = self._media_source_url(
                            self._gif_snapshot_filename, timestamp
                        )
                        attributes["entity_picture"] = gif_url
                        self._attr_entity_picture = gif_url
                        
                        # If we also have a JPG, add it as an alternate
                        if jpg_path:
                            attributes["jpg_picture"] = self._media_source_url(
                                self._jpg_snapshot_filename, timestamp
                            )
                    elif jpg_path:
                        # Fall back to JPG if GIF not available but we wanted both
                        jpg_url = self._media_source_url(
                            self._jpg_snapshot_filename, timestamp
                        )
                        attributes["entity_picture"] = jpg_url
                        self._attr_entity_picture = jpg_url
                else:
                    # Fallback to using the mp4 (may not render in picture card)
                    picture_url = self._media_source_url(
                        self._video_filename, timestamp
                    )
                    attributes["entity_picture"] = picture_url
                    self._attr_entity_picture = picture_url
                
        return attributes
