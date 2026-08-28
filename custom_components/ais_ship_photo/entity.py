"""Shared entity helpers for AIS Ship Photo."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import CONF_SEARXNG_URL, DOMAIN
from .coordinator import ShipPhotoCoordinator


class AisShipPhotoEntity(Entity):
    """Base entity for the AIS Ship Photo service device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ShipPhotoCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize an AIS Ship Photo entity."""
        super().__init__()
        self.coordinator = coordinator
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            entry_type=DeviceEntryType.SERVICE,
            manufacturer="AIS Ship Tracker",
            model="AIS Ship Photo",
            configuration_url=(
                entry.options.get(CONF_SEARXNG_URL)
                or entry.data.get(CONF_SEARXNG_URL)
            ),
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe the entity to photo lookup updates."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )
