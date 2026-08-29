"""Sensor platform for AIS Ship Tracker."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import AisShipTrackerConfigEntry
from .areas import area_id, area_name, area_slug, configured_areas
from .entity import AisShipTrackerEntity, remove_legacy_entities, vessel_finder_url
from .tracker import AisTrackerCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AisShipTrackerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the persistent and optional map sensors."""
    tracker = entry.runtime_data.tracker
    remove_legacy_entities(hass, entry, {"last_passing_ship"})
    entities: list[SensorEntity] = [AisConnectionStatusSensor(entry)]
    entities.extend(
        LastPassingShipSensor(entry, area, index)
        for index, area in enumerate(configured_areas(tracker.settings), 1)
    )
    known: dict[str, AisMapShipSensor] = {}
    if tracker.map_entities_enabled:
        for mmsi, ship in tracker.ships.items():
            known[mmsi] = AisMapShipSensor(entry, tracker, mmsi, ship)
        entities.extend(known.values())
    async_add_entities(entities)
    entry.async_create_background_task(
        hass,
        _async_remove_orphaned_map_entities(hass, entry, set(known)),
        "ais_ship_tracker_cleanup_map_entities",
    )

    @callback
    def tracker_updated() -> None:
        """Add newly observed vessels and remove expired sensors."""
        if not tracker.map_entities_enabled:
            return
        for mmsi in set(known) - set(tracker.ships):
            entity = known.pop(mmsi)
            entry.async_create_background_task(
                hass,
                _async_remove_map_entity(hass, entity),
                "ais_ship_tracker_remove_map_entity",
            )
        new_entities = []
        for mmsi, ship in tracker.ships.items():
            if mmsi not in known:
                known[mmsi] = AisMapShipSensor(entry, tracker, mmsi, ship)
                new_entities.append(known[mmsi])
        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(tracker.async_add_listener(tracker_updated))


async def _async_remove_orphaned_map_entities(
    hass: HomeAssistant,
    entry: AisShipTrackerConfigEntry,
    active_mmsis: set[str],
) -> None:
    """Remove dynamic vessel entities left by a previous runtime."""
    await asyncio.sleep(0)
    registry = er.async_get(hass)
    removed = 0
    for registry_entry in list(
        registry.entities.get_entries_for_config_entry_id(entry.entry_id)
    ):
        if (
            registry_entry.platform == entry.domain
            and (registry_entry.unique_id or "").startswith("ais_ship_")
            and (registry_entry.unique_id or "").removeprefix("ais_ship_")
            not in active_mmsis
        ):
            registry.async_remove(registry_entry.entity_id)
            removed += 1
    if removed:
        _LOGGER.info("Removed %d stale AIS vessel entities", removed)


async def _async_remove_map_entity(
    hass: HomeAssistant, entity: "AisMapShipSensor"
) -> None:
    """Remove an expired vessel entity from state and the entity registry."""
    entity_id = entity.entity_id
    await entity.async_remove(force_remove=True)
    if entity_id:
        er.async_get(hass).async_remove(entity_id)


class LastPassingShipSensor(AisShipTrackerEntity, SensorEntity):
    """Expose the last vessel detected by AISStream."""

    _attr_has_entity_name = False
    _attr_icon = "mdi:ferry"
    _attr_name = "Last Passing Ship"

    def __init__(
        self, entry: AisShipTrackerConfigEntry, area: dict[str, Any], index: int
    ) -> None:
        """Initialize the last vessel sensor."""
        super().__init__(entry)
        self.area_id = area_id(area, index)
        self._attr_name = f"{area_name(area, index)} Last Passing Ship"
        self._attr_unique_id = f"last_passing_ship_{self.area_id}"
        self._attr_suggested_object_id = f"{area_slug(area, index)}_last_passing_ship"
        self.coordinator = entry.runtime_data.tracker

    @property
    def available(self) -> bool:
        """Return whether a vessel has been detected or restored."""
        return self.area_id in self.coordinator.last_ships

    @property
    def native_value(self) -> str | None:
        """Return the latest vessel name."""
        return self.coordinator.last_ships.get(self.area_id, {}).get("ship_name")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the latest vessel details."""
        attributes = dict(self.coordinator.last_ships.get(self.area_id, {}))
        url = vessel_finder_url(attributes.get("mmsi"))
        if url:
            attributes["vessel_finder_url"] = url
        return attributes

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
        attributes = {
            key: value for key, value in self._ship.items() if not key.startswith("_")
        }
        url = vessel_finder_url(attributes.get("mmsi"))
        if url:
            attributes["vessel_finder_url"] = url
        return attributes

    async def async_added_to_hass(self) -> None:
        """Subscribe to tracker updates."""
        await super().async_added_to_hass()
        if self.mmsi not in self.coordinator.ships:
            await _async_remove_map_entity(self.hass, self)
            return
        self.async_on_remove(self.coordinator.async_add_listener(self._updated))

    @callback
    def _updated(self) -> None:
        """Refresh this vessel from the coordinator."""
        if self.mmsi in self.coordinator.ships:
            self._ship = self.coordinator.ships[self.mmsi]
        self.async_write_ha_state()
