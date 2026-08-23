"""Custom component for managing Reolink camera recordings."""
from datetime import timedelta
import logging
import os

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.service import async_register_admin_service

from .const import (
    CONF_ACCESS_TOKEN,
    CONF_STORAGE_PATH,
    DATA_COORDINATOR,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_STORAGE_PATH,
    DOMAIN,
)
from .coordinator import ReolinkRecordingsCoordinator
from .frontend import setup_frontend
from .helpers import (
    is_www_storage_path,
    resolve_storage_path,
    validate_storage_path,
)
from .http import async_setup_http

_LOGGER = logging.getLogger(__name__)

# Media source is not a regular platform, it's registered separately
PLATFORMS = ["sensor"]

SERVICE_REFRESH_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): cv.string,
    }
)


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old config entries to the current version."""
    _LOGGER.debug(
        "Migrating %s from version %s", config_entry.title, config_entry.version
    )

    data = dict(config_entry.data)
    options = dict(config_entry.options)
    version = config_entry.version

    if version < 2:
        storage_path = options.get(CONF_STORAGE_PATH, DEFAULT_STORAGE_PATH)
        if storage_path == "www/reolink_recordings":
            options[CONF_STORAGE_PATH] = DEFAULT_STORAGE_PATH
            _LOGGER.info(
                "Migrating storage path from www/reolink_recordings to %s. "
                "Move existing recordings to the new directory or trigger a refresh "
                "to re-download them.",
                DEFAULT_STORAGE_PATH,
            )
        version = 2

    if version < 3:
        # Move long-lived token out of CONF_PASSWORD; drop unused CONF_USERNAME.
        if CONF_ACCESS_TOKEN not in data and CONF_PASSWORD in data:
            data[CONF_ACCESS_TOKEN] = data[CONF_PASSWORD]
        data.pop(CONF_PASSWORD, None)
        data.pop(CONF_USERNAME, None)
        version = 3

    hass.config_entries.async_update_entry(
        config_entry, data=data, options=options, version=version
    )
    _LOGGER.info("Migration of %s to version %s successful", config_entry.title, version)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Reolink Recordings from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Get configuration
    host = entry.data.get(CONF_HOST)
    access_token = entry.data.get(CONF_ACCESS_TOKEN) or entry.data.get(CONF_PASSWORD)
    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    storage_path = entry.options.get(CONF_STORAGE_PATH, DEFAULT_STORAGE_PATH)

    if error := validate_storage_path(hass, storage_path):
        raise ConfigEntryError(
            f"Invalid storage path '{storage_path}' ({error}). "
            f"Use a relative path under the HA config directory "
            f"(default: {DEFAULT_STORAGE_PATH}), or an absolute path "
            f"such as a /media or NAS mount."
        )

    if is_www_storage_path(hass, storage_path):
        _LOGGER.warning(
            "Recordings are stored under %s, which is publicly served at /local/. "
            "Prefer %s (or another path outside www/) and move your recordings to "
            "avoid exposing surveillance footage without authentication.",
            storage_path,
            DEFAULT_STORAGE_PATH,
        )

    # Create storage directory if it doesn't exist
    storage_dir = resolve_storage_path(hass, storage_path)
    os.makedirs(storage_dir, exist_ok=True)

    # Create data coordinator
    coordinator = ReolinkRecordingsCoordinator(
        hass,
        entry.entry_id,
        host,
        access_token,
        storage_dir,
        entry=entry,  # Pass the entire config entry for access to options
    )

    # Initial data fetch on startup to ensure sensors have data
    # Without this, sensors may show as "unavailable" until the first scheduled refresh
    await coordinator.async_refresh()

    # Set up periodic update
    entry.async_on_unload(
        async_track_time_interval(
            hass, coordinator.async_refresh, timedelta(minutes=scan_interval)
        )
    )

    # Store the coordinator
    hass.data[DOMAIN][entry.entry_id] = {
        DATA_COORDINATOR: coordinator,
    }

    # Register the parent/hub device
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name="Reolink Recordings Hub",
        manufacturer="Reolink",
        model="Recordings Integration",
        sw_version="1.0",
    )

    # Set up all platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register authenticated media API + frontend resources
    async_setup_http(hass)
    setup_frontend(hass)

    # Register services (once)
    await register_services(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        # Clean up coordinator resources
        coordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
        await coordinator.cleanup()
        hass.data[DOMAIN].pop(entry.entry_id)

        # Remove admin service when last entry is unloaded
        if not hass.data[DOMAIN] and hass.services.has_service(DOMAIN, "refresh"):
            hass.services.async_remove(DOMAIN, "refresh")

    return unload_ok


async def register_services(hass: HomeAssistant) -> None:
    """Register admin-only services for Reolink Recordings."""
    if hass.services.has_service(DOMAIN, "refresh"):
        return

    async def handle_refresh(call: ServiceCall) -> None:
        """Handle the manual refresh service call."""
        entry_id = call.data.get("entry_id")
        if entry_id:
            targets = [entry_id] if entry_id in hass.data[DOMAIN] else []
        else:
            targets = list(hass.data[DOMAIN])

        if not targets:
            _LOGGER.error(
                "No matching config entry for refresh service call (entry_id=%s)",
                entry_id,
            )
            return

        for target_id in targets:
            coordinator = hass.data[DOMAIN][target_id][DATA_COORDINATOR]
            _LOGGER.info("Manual refresh requested for Reolink Recordings (%s)", target_id)
            await coordinator.async_refresh()
            _LOGGER.info("Manual refresh completed for Reolink Recordings (%s)", target_id)

    async_register_admin_service(
        hass,
        DOMAIN,
        "refresh",
        handle_refresh,
        schema=SERVICE_REFRESH_SCHEMA,
    )


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
