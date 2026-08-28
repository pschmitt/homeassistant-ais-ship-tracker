"""Sensor platform for AIS Ship Tracker."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import AisShipTrackerConfigEntry
from .entity import AisShipTrackerEntity
from .tracker import AisTrackerCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AisShipTrackerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the persistent and optional map sensors."""
    del hass
    tracker = entry.runtime_data.tracker
    entities: list[SensorEntity] = [
        LastPassingShipSensor(entry),
        AisConnectionStatusSensor(entry),
    ]
    known: dict[str, AisMapShipSensor] = {}
    if tracker.map_entities_enabled:
        for mmsi, ship in tracker.ships.items():
            known[mmsi] = AisMapShipSensor(entry, tracker, mmsi, ship)
        entities.extend(known.values())
    async_add_entities(entities)

    @callback
    def tracker_updated() -> None:
        """Add newly observed vessels and refresh existing sensors."""
        if not tracker.map_entities_enabled:
            return
        new_entities = []
        for mmsi, ship in tracker.ships.items():
            if mmsi not in known:
                known[mmsi] = AisMapShipSensor(entry, tracker, mmsi, ship)
                new_entities.append(known[mmsi])
        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(tracker.async_add_listener(tracker_updated))


class LastPassingShipSensor(AisShipTrackerEntity, SensorEntity):
    """Expose the last vessel detected by AISStream."""

    _attr_has_entity_name = False
    _attr_icon = "mdi:ferry"
    _attr_name = "Last Passing Ship"

    def __init__(self, entry: AisShipTrackerConfigEntry) -> None:
        """Initialize the last vessel sensor."""
        super().__init__(entry)
        self._attr_unique_id = "last_passing_ship"
        self.coordinator = entry.runtime_data.tracker

    @property
    def available(self) -> bool:
        """Return whether a vessel has been detected or restored."""
        return self.coordinator.last_ship is not None

    @property
    def native_value(self) -> str | None:
        """Return the latest vessel name."""
        return (self.coordinator.last_ship or {}).get("ship_name")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the latest vessel details."""
        return self.coordinator.last_ship or {}

    async def async_added_to_hass(self) -> None:
        """Subscribe to tracker updates."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )


class AisConnectionStatusSensor(AisShipTrackerEntity, SensorEntity):
    """Expose the AISStream connection state."""

    _attr_has_entity_name = False
    _attr_icon = "mdi:lan-connect"
    _attr_name = "AIS Connection Status"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: AisShipTrackerConfigEntry) -> None:
        """Initialize the connection sensor."""
        super().__init__(entry)
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_unique_id = "ais_connection_status"
        self.coordinator = entry.runtime_data.tracker

    @property
    def native_value(self) -> str:
        """Return the current connection state."""
        return self.coordinator.connection_status

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return connection diagnostics."""
        return {"error": self.coordinator.connection_error}

    async def async_added_to_hass(self) -> None:
        """Subscribe to tracker updates."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )


class AisMapShipSensor(AisShipTrackerEntity, SensorEntity):
    """Expose one currently visible vessel for map cards and automations."""

    _attr_has_entity_name = False
    _attr_icon = "mdi:ferry"
    _attr_native_unit_of_measurement = "kn"

    def __init__(
        self,
        entry: AisShipTrackerConfigEntry,
        coordinator: AisTrackerCoordinator,
        mmsi: str,
        ship: dict[str, Any],
    ) -> None:
        """Initialize a vessel map sensor."""
        super().__init__(entry)
        self.coordinator = coordinator
        self.mmsi = mmsi
        self._attr_unique_id = f"ais_ship_{mmsi}"
        self._attr_suggested_object_id = f"ais_ship_{mmsi}"
        self._ship = ship

    @property
    def name(self) -> str:
        """Return the current vessel name."""
        return str(self._ship.get("ship_name") or f"AIS Ship {self.mmsi}")

    @property
    def available(self) -> bool:
        """Return whether this vessel is still inside the map timeout."""
        return self.mmsi in self.coordinator.ships

    @property
    def native_value(self) -> float | None:
        """Return the vessel speed in knots."""
        value = self._ship.get("speed_knots")
        return float(value) if isinstance(value, (int, float)) else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return vessel position and AIS details."""
        return {key: value for key, value in self._ship.items() if not key.startswith("_")}

    async def async_added_to_hass(self) -> None:
        """Subscribe to tracker updates."""
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.async_add_listener(self._updated))

    @callback
    def _updated(self) -> None:
        """Refresh this vessel from the coordinator."""
        if self.mmsi in self.coordinator.ships:
            self._ship = self.coordinator.ships[self.mmsi]
        self.async_write_ha_state()
