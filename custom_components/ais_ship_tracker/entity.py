"""Shared entity helpers for AIS Ship Tracker."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import CONF_SEARXNG_URL, DOMAIN
class AisShipTrackerEntity(Entity):
    """Base entity for the AIS Ship Tracker service device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
    ) -> None:
        """Initialize an AIS Ship Tracker entity."""
        super().__init__()
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            entry_type=DeviceEntryType.SERVICE,
            manufacturer="AIS Ship Tracker",
            model="AIS Ship Tracker",
            configuration_url=(
                entry.options.get(CONF_SEARXNG_URL)
                or entry.data.get(CONF_SEARXNG_URL)
            ),
        )
