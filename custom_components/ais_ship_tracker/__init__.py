"""Home Assistant integration for AIS vessel tracking."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.issue_registry import IssueSeverity

from .const import (
    CONF_SEARXNG_PASSWORD,
    CONF_SEARXNG_URL,
    CONF_SEARXNG_USERNAME,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import ShipPhotoCoordinator
from .tracker import AisTrackerCoordinator


@dataclass(slots=True)
class AisShipTrackerRuntime:
    """Runtime objects shared by the integration platforms."""

    tracker: AisTrackerCoordinator
    photo: ShipPhotoCoordinator | None


type AisShipTrackerConfigEntry = ConfigEntry[AisShipTrackerRuntime]


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
    tracker = AisTrackerCoordinator(
        hass,
        async_get_clientsession(hass),
        settings,
        entry.entry_id,
    )
    photo = (
        ShipPhotoCoordinator(
        hass,
        async_get_clientsession(hass),
            settings[CONF_SEARXNG_URL],
            tracker,
            settings.get(CONF_SEARXNG_USERNAME),
            settings.get(CONF_SEARXNG_PASSWORD),
            entry.entry_id,
        )
        if settings.get(CONF_SEARXNG_URL)
        else None
    )
    entry.runtime_data = AisShipTrackerRuntime(tracker=tracker, photo=photo)
    await tracker.async_start()

    platforms = ["sensor", "event"]
    if photo is not None:
        platforms.append("camera")
    await hass.config_entries.async_forward_entry_setups(entry, platforms)

    @callback
    def tracker_updated() -> None:
        """Refresh the photo only when a new vessel becomes last seen."""
        _update_config_issues(hass, entry, settings)
        if photo is None:
            return
        mmsi = str(tracker.last_ship.get("mmsi", "")) if tracker.last_ship else ""
        if mmsi == tracker_updated.last_mmsi:
            return
        tracker_updated.last_mmsi = mmsi
        entry.async_create_background_task(
            hass, photo.async_refresh(force=True), "ais_ship_tracker_refresh"
        )

    tracker_updated.last_mmsi = ""
    entry.async_on_unload(tracker.async_add_listener(tracker_updated))

    if photo is not None:
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
