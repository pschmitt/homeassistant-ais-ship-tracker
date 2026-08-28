"""Home Assistant integration for photos of the latest AIS vessel."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.issue_registry import IssueSeverity

from .const import (
    CONF_SEARXNG_PASSWORD,
    CONF_SEARXNG_URL,
    CONF_SEARXNG_USERNAME,
    CONF_VESSEL_ENTITY,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import ShipPhotoCoordinator

type AisShipTrackerConfigEntry = ConfigEntry[ShipPhotoCoordinator | None]


def _valid_url(value: str) -> bool:
    """Return whether a value is an HTTP(S) URL."""
    parsed_url = urlparse(value)
    return parsed_url.scheme in {"http", "https"} and bool(parsed_url.netloc)


def _update_config_issues(
    hass: HomeAssistant, entry: ConfigEntry, settings: dict[str, Any]
) -> None:
    """Create or clear actionable configuration issues."""
    vessel_issue_id = f"vessel_entity_missing_{entry.entry_id}"
    if hass.states.get(settings[CONF_VESSEL_ENTITY]) is None:
        ir.async_create_issue(
            hass,
            DOMAIN,
            vessel_issue_id,
            data={"entry_id": entry.entry_id},
            is_fixable=True,
            is_persistent=True,
            issue_domain=DOMAIN,
            severity=IssueSeverity.ERROR,
            translation_key="vessel_entity_missing",
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, vessel_issue_id)

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
    coordinator = None
    platforms = []
    if settings.get(CONF_SEARXNG_URL):
        coordinator = ShipPhotoCoordinator(
            hass,
            async_get_clientsession(hass),
            settings[CONF_SEARXNG_URL],
            settings[CONF_VESSEL_ENTITY],
            settings.get(CONF_SEARXNG_USERNAME),
            settings.get(CONF_SEARXNG_PASSWORD),
            entry.entry_id,
        )
        platforms = PLATFORMS
    entry.runtime_data = coordinator

    if platforms:
        await hass.config_entries.async_forward_entry_setups(entry, platforms)

    @callback
    def state_changed(event: Any) -> None:
        """Refresh the photo when the tracked vessel changes."""
        del event
        _update_config_issues(hass, entry, settings)
        if coordinator is not None:
            entry.async_create_background_task(
                hass,
                coordinator.async_refresh(force=True),
                "ais_ship_tracker_refresh",
            )

    remove_listener = async_track_state_change_event(
        hass,
        [settings[CONF_VESSEL_ENTITY]],
        state_changed,
    )
    entry.async_on_unload(remove_listener)

    if coordinator is not None:
        entry.async_create_background_task(
            hass,
            coordinator.async_refresh(),
            "ais_ship_tracker_initial_refresh",
        )
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: AisShipTrackerConfigEntry
) -> bool:
    """Unload AIS Ship Tracker."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    return unload_ok
