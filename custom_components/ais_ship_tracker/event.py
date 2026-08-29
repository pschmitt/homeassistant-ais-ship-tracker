"""Event platform for AIS Ship Tracker."""

from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import AisShipTrackerConfigEntry
from .areas import area_id, area_name, area_slug, configured_areas
from .entity import AisShipTrackerEntity, remove_legacy_entities, vessel_finder_url


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AisShipTrackerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one last-ship-updated event entity per area."""
    remove_legacy_entities(hass, entry, {"last_ship_updated"})
    tracker = entry.runtime_data.tracker
    async_add_entities(
        LastShipUpdatedEvent(entry, area, index)
        for index, area in enumerate(configured_areas(tracker.settings), 1)
    )


class LastShipUpdatedEvent(AisShipTrackerEntity, EventEntity):
    """Fire when the integration records a new last passing vessel."""

    _attr_event_types = ["ship_updated"]
    _attr_icon = "mdi:ferry"
    _attr_translation_key = "last_ship_updated"

    def __init__(
        self, entry: AisShipTrackerConfigEntry, area: dict[str, Any], index: int
    ) -> None:
        """Initialize the event entity."""
        runtime = entry.runtime_data
        assert runtime is not None
        self.coordinator = runtime.tracker
        self.area_id = area_id(area, index)
        self.area_name = area_name(area, index)
        self._attr_name = f"{self.area_name} Last Ship Updated"
        self._attr_unique_id = f"last_ship_updated_{self.area_id}"
        self._attr_suggested_object_id = f"{area_slug(area, index)}_last_ship_updated"
        super().__init__(entry)
        self._last_mmsi: str | None = None

    async def async_added_to_hass(self) -> None:
        """Subscribe to the tracked vessel entity."""
        await super().async_added_to_hass()
        last_ship = self.coordinator.last_ships.get(self.area_id)
        if last_ship is not None:
            self._last_mmsi = self._mmsi(last_ship)
        self.async_on_remove(self.coordinator.async_add_listener(self._tracker_updated))

    @callback
    def _tracker_updated(self) -> None:
        """Trigger for a newly recorded vessel."""
        ship = self.coordinator.last_ships.get(self.area_id)
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
                "area_id": self.area_id,
                "area_name": self.area_name,
                "vessel_finder_url": vessel_finder_url(mmsi),
            },
        )

    @staticmethod
    def _mmsi(attributes: dict[str, Any]) -> str | None:
        """Return a normalized MMSI from sensor attributes."""
        mmsi = attributes.get("mmsi")
        return str(mmsi) if mmsi else None
