"""Home Assistant integration for AIS vessel tracking."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.issue_registry import IssueSeverity

from .areas import area_id, area_name, configured_areas
from .const import (
    CONF_AREAS,
    CONF_LATITUDE_NORTH,
    CONF_LATITUDE_SOUTH,
    CONF_LONGITUDE_EAST,
    CONF_LONGITUDE_WEST,
    CONF_SEARXNG_PASSWORD,
    CONF_SEARXNG_URL,
    CONF_SEARXNG_USERNAME,
    CONF_ZONE_ENTITY,
    CONF_ZONE_RADIUS,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import ShipPhotoCoordinator
from .tracker import AisTrackerCoordinator
from .zone import async_remove_zones, async_sync_zones


@dataclass(slots=True)
class AisShipTrackerRuntime:
    """Runtime objects shared by the integration platforms."""

    tracker: AisTrackerCoordinator
    photos: dict[str, ShipPhotoCoordinator]


type AisShipTrackerConfigEntry = ConfigEntry[AisShipTrackerRuntime]


async def async_migrate_entry(
    hass: HomeAssistant, entry: AisShipTrackerConfigEntry
) -> bool:
    """Migrate legacy single-area entries to the multi-area format."""
    if entry.version < 3:
        settings = {**entry.data, **entry.options}
        data = dict(entry.data)
        data[CONF_AREAS] = configured_areas(settings)
        hass.config_entries.async_update_entry(entry, data=data, version=3)
    if entry.version < 4:
        legacy_area_keys = (
            CONF_LONGITUDE_WEST,
            CONF_LATITUDE_SOUTH,
            CONF_LONGITUDE_EAST,
            CONF_LATITUDE_NORTH,
            CONF_ZONE_RADIUS,
        )
        data = dict(entry.data)
        data_areas = []
        for area in configured_areas({**entry.data, **entry.options}):
            migrated_area = dict(area)
            if migrated_area.get(CONF_ZONE_ENTITY):
                for key in legacy_area_keys:
                    migrated_area.pop(key, None)
            data_areas.append(migrated_area)
        data[CONF_AREAS] = data_areas

        options = dict(entry.options)
        if CONF_AREAS in options:
            options[CONF_AREAS] = [dict(area) for area in data_areas]
        hass.config_entries.async_update_entry(
            entry, data=data, options=options, version=4
        )
    return True


def _valid_url(value: str) -> bool:
    """Return whether a value is an HTTP(S) URL."""
    parsed_url = urlparse(value)
    return parsed_url.scheme in {"http", "https"} and bool(parsed_url.netloc)


def _update_config_issues(
    hass: HomeAssistant, entry: ConfigEntry, settings: dict[str, Any]
) -> None:
    """Create or clear actionable configuration issues."""
    url_issue_id = f"invalid_searxng_url_{entry.entry_id}"
    searxng_url = settings.get(CONF_SEARXNG_URL, "")
    if not searxng_url or _valid_url(searxng_url):
        ir.async_delete_issue(hass, DOMAIN, url_issue_id)
    else:
        ir.async_create_issue(
            hass,
            DOMAIN,
            url_issue_id,
            data={"entry_id": entry.entry_id},
            is_fixable=True,
            is_persistent=True,
            issue_domain=DOMAIN,
            severity=IssueSeverity.ERROR,
            translation_key="invalid_searxng_url",
        )


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the integration domain."""
    del config
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: AisShipTrackerConfigEntry
) -> bool:
    """Set up AIS Ship Tracker from a config entry."""
    settings = {**entry.data, **entry.options}
    _update_config_issues(hass, entry, settings)
    await async_sync_zones(hass, entry.entry_id, settings)
    tracker = AisTrackerCoordinator(
        hass,
        async_get_clientsession(hass),
        settings,
        entry.entry_id,
    )
    photos: dict[str, ShipPhotoCoordinator] = {}
    if settings.get(CONF_SEARXNG_URL):
        photos = {
            area_id(area, index): ShipPhotoCoordinator(
                hass,
                async_get_clientsession(hass),
                settings[CONF_SEARXNG_URL],
                tracker,
                settings.get(CONF_SEARXNG_USERNAME),
                settings.get(CONF_SEARXNG_PASSWORD),
                entry.entry_id,
                area_id(area, index),
                area_name(area, index),
            )
            for index, area in enumerate(configured_areas(settings), 1)
        }
    entry.runtime_data = AisShipTrackerRuntime(tracker=tracker, photos=photos)
    await tracker.async_start()

    source_zones = {
        str(area[CONF_ZONE_ENTITY])
        for area in configured_areas(settings)
        if area.get(CONF_ZONE_ENTITY)
    }

    async def async_refresh_source_zone() -> None:
        """Refresh the mirrored zone and AIS subscription."""
        await async_sync_zones(hass, entry.entry_id, settings)
        await tracker.async_restart()

    @callback
    def source_zone_changed(event: Any) -> None:
        """Refresh the AIS rectangle when a source zone changes."""
        del event
        entry.async_create_background_task(
            hass,
            async_refresh_source_zone(),
            "ais_ship_tracker_zone_changed",
        )

    if source_zones:
        entry.async_on_unload(
            async_track_state_change_event(hass, source_zones, source_zone_changed)
        )

    platforms = ["sensor", "event"]
    if photos:
        platforms.append("camera")
    await hass.config_entries.async_forward_entry_setups(entry, platforms)

    @callback
    def tracker_updated() -> None:
        """Refresh the photo only when a new vessel becomes last seen."""
        _update_config_issues(hass, entry, settings)
        if not photos:
            return
        for tracking_area_id, photo in photos.items():
            last_ship = tracker.last_ships.get(tracking_area_id)
            mmsi = str(last_ship.get("mmsi", "")) if last_ship else ""
            if mmsi == tracker_updated.last_mmsis.get(tracking_area_id):
                continue
            tracker_updated.last_mmsis[tracking_area_id] = mmsi
            entry.async_create_background_task(
                hass, photo.async_refresh(force=True), "ais_ship_tracker_refresh"
            )

    tracker_updated.last_mmsis = {}
    entry.async_on_unload(tracker.async_add_listener(tracker_updated))

    for photo in photos.values():
        entry.async_create_background_task(
            hass, photo.async_refresh(), "ais_ship_tracker_initial_refresh"
        )
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: AisShipTrackerConfigEntry
) -> bool:
    """Unload AIS Ship Tracker."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if entry.runtime_data is not None:
        await entry.runtime_data.tracker.async_stop()
    return unload_ok


async def async_remove_entry(
    hass: HomeAssistant, entry: AisShipTrackerConfigEntry
) -> None:
    """Remove integration-owned resources with the config entry."""
    await async_remove_zones(hass, entry.entry_id)
