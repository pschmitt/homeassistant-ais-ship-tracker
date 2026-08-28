"""Camera platform for AIS Ship Tracker."""

from __future__ import annotations

from homeassistant.components.camera import Camera
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import AisShipTrackerConfigEntry
from .coordinator import ShipPhotoCoordinator
from .entity import AisShipTrackerEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AisShipTrackerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the AIS ship photo camera."""
    del hass
    async_add_entities([ShipPhotoCamera(entry.runtime_data, entry)])


class ShipPhotoCamera(AisShipTrackerEntity, Camera):
    """Camera showing the latest AIS vessel photo."""

    _attr_icon = "mdi:ferry"
    _attr_translation_key = "last_passing_ship_photo"

    def __init__(
        self,
        coordinator: ShipPhotoCoordinator,
        entry: AisShipTrackerConfigEntry,
    ) -> None:
        self._attr_unique_id = "last_passing_ship_photo"
        AisShipTrackerEntity.__init__(self, coordinator, entry)

    @property
    def available(self) -> bool:
        """Return whether a photo is currently cached."""
        return self.coordinator.available

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
