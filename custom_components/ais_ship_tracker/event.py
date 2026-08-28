"""Event platform for AIS Ship Tracker."""

from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from . import AisShipTrackerConfigEntry
from .entity import AisShipTrackerEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AisShipTrackerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the last-ship-updated event entity."""
    async_add_entities([LastShipUpdatedEvent(hass, entry)])


class LastShipUpdatedEvent(AisShipTrackerEntity, EventEntity):
    """Fire when the add-on records a new last passing vessel."""

    _attr_event_types = ["ship_updated"]
    _attr_icon = "mdi:ferry"
    _attr_translation_key = "last_ship_updated"

    def __init__(self, hass: HomeAssistant, entry: AisShipTrackerConfigEntry) -> None:
        """Initialize the event entity."""
        coordinator = entry.runtime_data
        assert coordinator is not None
        super().__init__(coordinator, entry)
        self._hass = hass
        self._attr_unique_id = "last_ship_updated"
        self._last_mmsi: str | None = None

    async def async_added_to_hass(self) -> None:
        """Subscribe to the tracked vessel entity."""
        await super().async_added_to_hass()
        state = self._hass.states.get(self.coordinator.vessel_entity)
        if state is not None:
            self._last_mmsi = self._mmsi(state.attributes)
        self.async_on_remove(
            async_track_state_change_event(
                self._hass,
                [self.coordinator.vessel_entity],
                self._state_changed,
            )
        )

    @callback
    def _state_changed(self, event: Any) -> None:
        """Trigger for a newly recorded vessel."""
        new_state = event.data.get("new_state")
        if new_state is None:
            return
        mmsi = self._mmsi(new_state.attributes)
        if not mmsi or mmsi == self._last_mmsi:
            return
        self._last_mmsi = mmsi
        attributes = new_state.attributes
        self._trigger_event(
            "ship_updated",
            {
                "ship_name": attributes.get("ship_name") or new_state.state,
                "mmsi": mmsi,
                "latitude": attributes.get("latitude"),
                "longitude": attributes.get("longitude"),
                "speed_knots": attributes.get("speed_knots"),
                "course": attributes.get("course"),
                "heading": attributes.get("heading"),
                "navigational_status": attributes.get("navigational_status"),
                "vessel_class": attributes.get("vessel_class"),
                "spotted_time": attributes.get("spotted_time"),
            },
        )

    @staticmethod
    def _mmsi(attributes: dict[str, Any]) -> str | None:
        """Return a normalized MMSI from sensor attributes."""
        mmsi = attributes.get("mmsi")
        return str(mmsi) if mmsi else None
