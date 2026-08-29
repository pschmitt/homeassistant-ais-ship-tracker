"""Diagnostics support for AIS Ship Tracker."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import AisShipTrackerConfigEntry
from .areas import configured_areas
from .const import (CONF_API_KEY, CONF_ENABLE_MAP_ENTITIES,
                    CONF_INCLUDE_CLASS_B, CONF_MAP_TIMEOUT_MINUTES,
                    CONF_MAX_MAP_ENTITIES, CONF_SEARXNG_PASSWORD,
                    CONF_SEARXNG_URL, CONF_SEARXNG_USERNAME,
                    CONF_VESSEL_WATCHLIST)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    config_entry: AisShipTrackerConfigEntry,
) -> dict[str, Any]:
    """Return safe diagnostics for an AIS Ship Tracker config entry."""
    del hass
    runtime = config_entry.runtime_data
    tracker = runtime.tracker
    photos = runtime.photos
    settings = {**config_entry.data, **config_entry.options}
    cameras = {
        area_id: {
            "available": photo.available,
            "attributes": photo.attributes,
            "image_size": len(photo.image or b""),
        }
        for area_id, photo in photos.items()
    }
    return {
        "entry": {
            "title": config_entry.title,
            "data": async_redact_data(dict(config_entry.data), {CONF_SEARXNG_PASSWORD}),
            "options": async_redact_data(
                dict(config_entry.options), {CONF_SEARXNG_PASSWORD}
            ),
        },
        "settings": {
            CONF_API_KEY: "REDACTED" if settings.get(CONF_API_KEY) else None,
            CONF_ENABLE_MAP_ENTITIES: settings.get(CONF_ENABLE_MAP_ENTITIES),
            CONF_INCLUDE_CLASS_B: settings.get(CONF_INCLUDE_CLASS_B),
            CONF_VESSEL_WATCHLIST: settings.get(CONF_VESSEL_WATCHLIST),
            CONF_MAP_TIMEOUT_MINUTES: settings.get(CONF_MAP_TIMEOUT_MINUTES),
            CONF_MAX_MAP_ENTITIES: settings.get(CONF_MAX_MAP_ENTITIES, 10),
            CONF_SEARXNG_URL: settings.get(CONF_SEARXNG_URL),
            CONF_SEARXNG_USERNAME: settings.get(CONF_SEARXNG_USERNAME),
            "areas": configured_areas(settings),
        },
        "tracker": {
            "connection_status": tracker.connection_status,
            "connection_error": tracker.connection_error,
            "last_ships": tracker.last_ships,
            "map_ship_count": len(tracker.ships),
        },
        "cameras": cameras,
    }
