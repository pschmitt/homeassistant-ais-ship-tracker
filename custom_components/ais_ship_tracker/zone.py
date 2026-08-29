"""Manage passive Home Assistant zones representing AIS target areas."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components import zone as zone_component
from homeassistant.components.zone.const import CONF_PASSIVE
from homeassistant.const import (CONF_ICON, CONF_LATITUDE, CONF_LONGITUDE,
                                 CONF_NAME, CONF_RADIUS)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .areas import configured_areas
from .const import DOMAIN, ZONE_NAME

# Keep the HA Store schema version stable; the payload migration below is
# handled by this module rather than by Home Assistant's generic Store.
_STORE_VERSION = 1
_LOGGER = logging.getLogger(__name__)


def _store(hass: HomeAssistant, entry_id: str) -> Store[dict[str, Any]]:
    """Return the store used to remember generated zone IDs."""
    return Store(hass, _STORE_VERSION, f"{DOMAIN}.zone_{entry_id}")


def _zone_name(area: dict[str, Any], index: int) -> str:
    """Return a stable, human-readable zone name for one area."""
    if index == 1:
        return ZONE_NAME
    return f"{ZONE_NAME} ({area.get('name', f'Area {index}')})"


def _zone_data(
    area: dict[str, Any], index: int, home_location: tuple[float, float, float] | None
) -> dict[str, Any]:
    """Build zone configuration from one configured AIS area."""
    if index == 1 and home_location is not None:
        latitude, longitude, radius = home_location
    else:
        latitude = (float(area["latitude_south"]) + float(area["latitude_north"])) / 2
        longitude = (
            float(area["longitude_west"]) + float(area["longitude_east"])
        ) / 2
        radius = float(area.get("zone_radius", 100))
    return {
        CONF_NAME: _zone_name(area, index),
        CONF_LATITUDE: latitude,
        CONF_LONGITUDE: longitude,
        CONF_RADIUS: radius,
        CONF_ICON: "mdi:ferry",
        CONF_PASSIVE: True,
    }


async def async_sync_zones(
    hass: HomeAssistant, entry_id: str, settings: dict[str, Any]
) -> None:
    """Create or update all integration-owned passive target zones."""
    collection = hass.data.get(zone_component.DATA_ZONE_STORAGE_COLLECTION)
    if collection is None:
        _LOGGER.warning("The Home Assistant zone storage collection is unavailable")
        return

    store = _store(hass, entry_id)
    stored = await store.async_load()
    zone_ids: dict[str, str] = {}
    if isinstance(stored, dict):
        if isinstance(stored.get("zone_ids"), dict):
            zone_ids = {
                str(area_id): str(zone_id)
                for area_id, zone_id in stored["zone_ids"].items()
            }
        elif stored.get("zone_id"):
            # Migrate the original single-zone store format.
            zone_ids["area_1"] = str(stored["zone_id"])

    areas = configured_areas(settings)
    home = hass.states.get("zone.home")
    home_location = None
    if home is not None:
        try:
            home_location = (
                float(home.attributes[CONF_LATITUDE]),
                float(home.attributes[CONF_LONGITUDE]),
                float(home.attributes[CONF_RADIUS]),
            )
        except (KeyError, TypeError, ValueError):
            _LOGGER.warning("Home zone has incomplete location data")
    desired_area_ids = {
        str(area.get("id", f"area_{index}")) for index, area in enumerate(areas, 1)
    }
    for area_index, area in enumerate(areas, 1):
        area_id = str(area.get("id", f"area_{area_index}"))
        data = _zone_data(area, area_index, home_location)
        zone_id = zone_ids.get(area_id)
        if zone_id and zone_id in collection.data:
            await collection.async_update_item(zone_id, data)
            continue
        item = await collection.async_create_item(data)
        zone_ids[area_id] = item["id"]

    for area_id, zone_id in list(zone_ids.items()):
        if area_id not in desired_area_ids and zone_id in collection.data:
            await collection.async_delete_item(zone_id)
        if area_id not in desired_area_ids:
            zone_ids.pop(area_id, None)
    await store.async_save({"zone_ids": zone_ids})


async def async_remove_zones(hass: HomeAssistant, entry_id: str) -> None:
    """Remove all generated zones when the integration is removed."""
    collection = hass.data.get(zone_component.DATA_ZONE_STORAGE_COLLECTION)
    if collection is None:
        return

    store = _store(hass, entry_id)
    stored = await store.async_load()
    zone_ids: set[str] = set()
    if isinstance(stored, dict):
        if isinstance(stored.get("zone_ids"), dict):
            zone_ids.update(str(zone_id) for zone_id in stored["zone_ids"].values())
        if stored.get("zone_id"):
            zone_ids.add(str(stored["zone_id"]))
    for zone_id in zone_ids:
        if zone_id in collection.data:
            await collection.async_delete_item(zone_id)
    await store.async_remove()


# Compatibility aliases for callers from the single-area implementation.
async_sync_zone = async_sync_zones
async_remove_zone = async_remove_zones
