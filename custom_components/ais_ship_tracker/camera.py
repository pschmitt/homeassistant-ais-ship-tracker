"""Camera platform for AIS Ship Tracker."""

from __future__ import annotations

from typing import Any

from homeassistant.components.camera import Camera
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import AisShipTrackerConfigEntry
from .areas import area_id, area_name, area_slug, configured_areas
from .coordinator import ShipPhotoCoordinator
from .entity import AisShipTrackerEntity, remove_legacy_entities


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AisShipTrackerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one AIS ship photo camera per tracking area."""
    assert entry.runtime_data is not None
    remove_legacy_entities(hass, entry, {"last_passing_ship_photo"})
    async_add_entities(
        ShipPhotoCamera(
            entry.runtime_data.photos[area_id(area, index)], entry, area, index
        )
        for index, area in enumerate(
            configured_areas(entry.runtime_data.tracker.settings), 1
        )
    )


class ShipPhotoCamera(AisShipTrackerEntity, Camera):
    """Camera showing the latest AIS vessel photo."""

    _attr_icon = "mdi:ferry"
    _attr_translation_key = "last_passing_ship_photo"

    def __init__(
        self,
        coordinator: ShipPhotoCoordinator,
        entry: AisShipTrackerConfigEntry,
        area: dict[str, Any],
        index: int,
    ) -> None:
        self.area_id = area_id(area, index)
        self._attr_name = f"{area_name(area, index)} Last Passing Ship Photo"
        self._attr_unique_id = f"last_passing_ship_photo_{self.area_id}"
        self._attr_suggested_object_id = (
            f"{area_slug(area, index)}_last_passing_ship_photo"
        )
        self.coordinator = coordinator
        AisShipTrackerEntity.__init__(self, entry)

    async def async_added_to_hass(self) -> None:
        """Subscribe to photo lookup updates."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )

    @property
    def available(self) -> bool:
        """Return whether the configured photo lookup camera is available."""
        return True

    @property
    def extra_state_attributes(self):
        """Expose lookup details for debugging."""
        return self.coordinator.attributes

    async def async_camera_image(self, width=None, height=None) -> bytes | None:
        """Return the cached vessel photo."""
        if self.coordinator.needs_refresh:
            await self.coordinator.async_refresh()
        self.content_type = self.coordinator.content_type
        return self.coordinator.image
