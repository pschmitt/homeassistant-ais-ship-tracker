"""Diagnostics support for AIS Ship Tracker."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import AisShipTrackerConfigEntry
from .const import (
    CONF_API_KEY,
    CONF_ENABLE_MAP_ENTITIES,
    CONF_INCLUDE_CLASS_B,
    CONF_LATITUDE_NORTH,
    CONF_LATITUDE_SOUTH,
    CONF_LONGITUDE_EAST,
    CONF_LONGITUDE_WEST,
    CONF_MAP_TIMEOUT_MINUTES,
    CONF_SEARXNG_PASSWORD,
    CONF_SEARXNG_URL,
    CONF_SEARXNG_USERNAME,
    CONF_VESSEL_WATCHLIST,
)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    config_entry: AisShipTrackerConfigEntry,
) -> dict[str, Any]:
    """Return safe diagnostics for an AIS Ship Tracker config entry."""
    del hass
    runtime = config_entry.runtime_data
    tracker = runtime.tracker
    photo = runtime.photo
    settings = {**config_entry.data, **config_entry.options}
    camera = {
        "available": photo.available if photo else False,
        "attributes": photo.attributes if photo else {},
        "image_size": len(photo.image or b"") if photo else 0,
    }
    return {
        "entry": {
            "title": config_entry.title,
            "data": async_redact_data(
                dict(config_entry.data), {CONF_SEARXNG_PASSWORD}
            ),
            "options": async_redact_data(
                dict(config_entry.options), {CONF_SEARXNG_PASSWORD}
            ),
        },
        "settings": {
            CONF_API_KEY: "REDACTED" if settings.get(CONF_API_KEY) else None,
            CONF_LONGITUDE_WEST: settings.get(CONF_LONGITUDE_WEST),
            CONF_LATITUDE_SOUTH: settings.get(CONF_LATITUDE_SOUTH),
            CONF_LONGITUDE_EAST: settings.get(CONF_LONGITUDE_EAST),
            CONF_LATITUDE_NORTH: settings.get(CONF_LATITUDE_NORTH),
            CONF_ENABLE_MAP_ENTITIES: settings.get(CONF_ENABLE_MAP_ENTITIES),
            CONF_INCLUDE_CLASS_B: settings.get(CONF_INCLUDE_CLASS_B),
            CONF_VESSEL_WATCHLIST: settings.get(CONF_VESSEL_WATCHLIST),
            CONF_MAP_TIMEOUT_MINUTES: settings.get(CONF_MAP_TIMEOUT_MINUTES),
            CONF_SEARXNG_URL: settings.get(CONF_SEARXNG_URL),
            CONF_SEARXNG_USERNAME: settings.get(CONF_SEARXNG_USERNAME),
        },
        "tracker": {
            "connection_status": tracker.connection_status,
            "connection_error": tracker.connection_error,
            "last_ship": tracker.last_ship,
            "map_ship_count": len(tracker.ships),
        },
        "camera": camera,
    }
