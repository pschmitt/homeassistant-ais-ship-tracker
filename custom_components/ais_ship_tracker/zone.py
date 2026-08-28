"""Manage the passive Home Assistant zone representing the AIS target area."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components import zone as zone_component
from homeassistant.const import (
    CONF_ICON,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_NAME,
    CONF_RADIUS,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from homeassistant.components.zone.const import CONF_PASSIVE

from .const import (
    CONF_LATITUDE_NORTH,
    CONF_LATITUDE_SOUTH,
    CONF_LONGITUDE_EAST,
    CONF_LONGITUDE_WEST,
    CONF_ZONE_RADIUS,
    DOMAIN,
    ZONE_NAME,
)

_STORE_VERSION = 1
_LOGGER = logging.getLogger(__name__)


def _store(hass: HomeAssistant, entry_id: str) -> Store[dict[str, str]]:
    """Return the store used to remember the generated zone ID."""
    return Store(hass, _STORE_VERSION, f"{DOMAIN}.zone_{entry_id}")


def _zone_data(settings: dict[str, Any]) -> dict[str, Any]:
    """Build the zone configuration from the configured AIS bounding box."""
    return {
        CONF_NAME: ZONE_NAME,
        CONF_LATITUDE: (
            float(settings[CONF_LATITUDE_SOUTH])
            + float(settings[CONF_LATITUDE_NORTH])
        )
        / 2,
        CONF_LONGITUDE: (
            float(settings[CONF_LONGITUDE_WEST])
            + float(settings[CONF_LONGITUDE_EAST])
        )
        / 2,
        CONF_RADIUS: float(settings.get(CONF_ZONE_RADIUS, 100)),
        CONF_ICON: "mdi:ferry",
        CONF_PASSIVE: True,
    }


async def async_sync_zone(
    hass: HomeAssistant, entry_id: str, settings: dict[str, Any]
) -> None:
    """Create or update the integration-owned passive target zone."""
    collection = hass.data.get(zone_component.DATA_ZONE_STORAGE_COLLECTION)
    if collection is None:
        _LOGGER.warning("The Home Assistant zone storage collection is unavailable")
        return

    store = _store(hass, entry_id)
    stored = await store.async_load()
    zone_id = stored.get("zone_id") if isinstance(stored, dict) else None
    data = _zone_data(settings)

    if zone_id and zone_id in collection.data:
        await collection.async_update_item(zone_id, data)
        return

    item = await collection.async_create_item(data)
    await store.async_save({"zone_id": item["id"]})


async def async_remove_zone(hass: HomeAssistant, entry_id: str) -> None:
    """Remove the generated zone when the integration is removed."""
    collection = hass.data.get(zone_component.DATA_ZONE_STORAGE_COLLECTION)
    if collection is None:
        return

    store = _store(hass, entry_id)
    stored = await store.async_load()
    zone_id = stored.get("zone_id") if isinstance(stored, dict) else None
    if zone_id and zone_id in collection.data:
        await collection.async_delete_item(zone_id)
    await store.async_remove()
