"""Event platform for AIS Ship Tracker."""

from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import AisShipTrackerConfigEntry
from .entity import AisShipTrackerEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AisShipTrackerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the last-ship-updated event entity."""
    async_add_entities([LastShipUpdatedEvent(entry)])


class LastShipUpdatedEvent(AisShipTrackerEntity, EventEntity):
    """Fire when the add-on records a new last passing vessel."""

    _attr_event_types = ["ship_updated"]
    _attr_icon = "mdi:ferry"
    _attr_translation_key = "last_ship_updated"

    def __init__(self, entry: AisShipTrackerConfigEntry) -> None:
        """Initialize the event entity."""
        runtime = entry.runtime_data
        assert runtime is not None
        self.coordinator = runtime.tracker
        super().__init__(entry)
        self._attr_unique_id = "last_ship_updated"
        self._last_mmsi: str | None = None

    async def async_added_to_hass(self) -> None:
        """Subscribe to the tracked vessel entity."""
        await super().async_added_to_hass()
        if self.coordinator.last_ship is not None:
            self._last_mmsi = self._mmsi(self.coordinator.last_ship)
        self.async_on_remove(self.coordinator.async_add_listener(self._tracker_updated))

    @callback
    def _tracker_updated(self) -> None:
        """Trigger for a newly recorded vessel."""
        ship = self.coordinator.last_ship
        if ship is None:
            return
        mmsi = self._mmsi(ship)
        if not mmsi or mmsi == self._last_mmsi:
            return
        self._last_mmsi = mmsi
        self._trigger_event(
            "ship_updated",
            {
                "ship_name": ship.get("ship_name"),
                "mmsi": mmsi,
                "latitude": ship.get("latitude"),
                "longitude": ship.get("longitude"),
                "speed_knots": ship.get("speed_knots"),
                "course": ship.get("course"),
                "heading": ship.get("heading"),
                "navigational_status": ship.get("navigational_status"),
                "vessel_class": ship.get("vessel_class"),
                "spotted_time": ship.get("spotted_time"),
            },
        )

    @staticmethod
    def _mmsi(attributes: dict[str, Any]) -> str | None:
        """Return a normalized MMSI from sensor attributes."""
        mmsi = attributes.get("mmsi")
        return str(mmsi) if mmsi else None
