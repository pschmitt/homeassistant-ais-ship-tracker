"""Diagnostics support for AIS Ship Tracker."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import AisShipTrackerConfigEntry
from .const import (
    CONF_SEARXNG_PASSWORD,
    CONF_SEARXNG_URL,
    CONF_SEARXNG_USERNAME,
    CONF_VESSEL_ENTITY,
)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    config_entry: AisShipTrackerConfigEntry,
) -> dict[str, Any]:
    """Return safe diagnostics for an AIS Ship Tracker config entry."""
    del hass
    coordinator = config_entry.runtime_data
    settings = {**config_entry.data, **config_entry.options}
    camera = {
        "available": coordinator.available,
        "attributes": coordinator.attributes,
        "image_size": len(coordinator.image or b""),
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
            CONF_SEARXNG_URL: settings.get(CONF_SEARXNG_URL),
            CONF_SEARXNG_USERNAME: settings.get(CONF_SEARXNG_USERNAME),
            CONF_VESSEL_ENTITY: settings.get(CONF_VESSEL_ENTITY),
        },
        "camera": camera,
    }
