"""Config flow for AIS Ship Tracker."""

from __future__ import annotations

from math import cos, radians
from typing import Any
from urllib.parse import urlparse

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, OptionsFlowWithReload
from homeassistant.core import callback
from homeassistant.helpers.selector import (BooleanSelector, NumberSelector,
                                            NumberSelectorConfig, TextSelector,
                                            TextSelectorConfig,
                                            TextSelectorType, SelectSelector,
                                            SelectSelectorConfig)

from .areas import area_form_defaults, area_from_form, configured_areas
from .const import (CONF_API_KEY, CONF_AREA_COUNT, CONF_AREA_NAME, CONF_AREAS,
                    CONF_ENABLE_MAP_ENTITIES, CONF_INCLUDE_CLASS_B,
                    CONF_LATITUDE_NORTH, CONF_LATITUDE_SOUTH,
                    CONF_LONGITUDE_EAST, CONF_LONGITUDE_WEST,
                    CONF_MAP_TIMEOUT_MINUTES, CONF_MAX_MAP_ENTITIES,
                    CONF_SEARXNG_PASSWORD, CONF_SEARXNG_URL,
                    CONF_SEARXNG_USERNAME, CONF_VESSEL_WATCHLIST,
                    CONF_ZONE_RADIUS, DOMAIN)

_MAX_AREAS = 10


def _valid_url(value: str) -> bool:
    """Return whether a value is an HTTP(S) URL."""
    parsed_url = urlparse(value.strip())
    return parsed_url.scheme in {"http", "https"} and bool(parsed_url.hostname)


def _normalize_url(value: str) -> str:
    """Normalize a configured SearXNG URL."""
    return value.strip().rstrip("/")


def _common_schema(
    defaults: dict[str, Any] | None = None,
    *,
    api_key_required: bool,
    include_area_count: bool = True,
) -> vol.Schema:
    """Return the shared, non-area integration settings schema."""
    defaults = defaults or {}
    schema: dict[Any, Any] = {
        (
            vol.Required(CONF_API_KEY)
            if api_key_required
            else vol.Optional(CONF_API_KEY)
        ): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
        vol.Required(CONF_ENABLE_MAP_ENTITIES, default=True): BooleanSelector(),
        vol.Required(CONF_INCLUDE_CLASS_B, default=True): BooleanSelector(),
        vol.Optional(CONF_VESSEL_WATCHLIST, default=""): TextSelector(),
        vol.Required(CONF_MAP_TIMEOUT_MINUTES, default=30): NumberSelector(
            NumberSelectorConfig(min=5, max=1440, step=1)
        ),
        vol.Required(CONF_MAX_MAP_ENTITIES, default=10): NumberSelector(
            NumberSelectorConfig(min=0, max=50, step=1, mode="slider")
        ),
        vol.Optional(CONF_SEARXNG_URL, default=""): TextSelector(),
        vol.Optional(CONF_SEARXNG_USERNAME): TextSelector(),
        vol.Optional(CONF_SEARXNG_PASSWORD): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
    }
    if include_area_count:
        schema[
            vol.Required(CONF_AREA_COUNT, default=defaults.get(CONF_AREA_COUNT, 1))
        ] = NumberSelector(
            NumberSelectorConfig(min=1, max=_MAX_AREAS, step=1, mode="slider")
        )
    return vol.Schema(schema)


def _area_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Return the schema for one named tracking area."""
    defaults = defaults or {}
    longitude = NumberSelectorConfig(min=-180, max=180, step=0.001, mode="box")
    latitude = NumberSelectorConfig(min=-90, max=90, step=0.001, mode="box")
    return vol.Schema(
        {
            vol.Required(
                CONF_AREA_NAME, default=defaults.get(CONF_AREA_NAME, "Home")
            ): TextSelector(),
            vol.Required(
                CONF_LONGITUDE_WEST, default=defaults.get(CONF_LONGITUDE_WEST, 0)
            ): NumberSelector(longitude),
            vol.Required(
                CONF_LATITUDE_SOUTH, default=defaults.get(CONF_LATITUDE_SOUTH, 0)
            ): NumberSelector(latitude),
            vol.Required(
                CONF_LONGITUDE_EAST, default=defaults.get(CONF_LONGITUDE_EAST, 0)
            ): NumberSelector(longitude),
            vol.Required(
                CONF_LATITUDE_NORTH, default=defaults.get(CONF_LATITUDE_NORTH, 0)
            ): NumberSelector(latitude),
            vol.Required(
                CONF_ZONE_RADIUS, default=defaults.get(CONF_ZONE_RADIUS, 100)
            ): NumberSelector(
                NumberSelectorConfig(min=1, max=100000, step=1, mode="box")
            ),
        }
    )


def _validate_common_input(user_input: dict[str, Any]) -> str | None:
    """Validate settings that selectors cannot express."""
    api_key = str(user_input.get(CONF_API_KEY, "")).strip()
    if not api_key or set(api_key) == {"*"}:
        return "invalid_api_key"
    if user_input.get(CONF_SEARXNG_URL) and not _valid_url(
        user_input[CONF_SEARXNG_URL]
    ):
        return "invalid_url"
    return None


def _validate_area(user_input: dict[str, Any]) -> str | None:
    """Validate one tracking area."""
    if not str(user_input.get(CONF_AREA_NAME, "")).strip():
        return "invalid_area_name"
    if user_input[CONF_LATITUDE_SOUTH] >= user_input[CONF_LATITUDE_NORTH]:
        return "invalid_bounds"
    if user_input[CONF_LONGITUDE_WEST] >= user_input[CONF_LONGITUDE_EAST]:
        return "invalid_bounds"
    if float(user_input.get(CONF_ZONE_RADIUS, 0)) <= 0:
        return "invalid_radius"
    return None


def _clean_common_input(user_input: dict[str, Any]) -> dict[str, Any]:
    """Normalize common settings and remove blank optional secrets."""
    cleaned = dict(user_input)
    cleaned[CONF_SEARXNG_URL] = _normalize_url(cleaned.get(CONF_SEARXNG_URL, ""))
    if not cleaned.get(CONF_SEARXNG_PASSWORD):
        cleaned.pop(CONF_SEARXNG_PASSWORD, None)
    cleaned[CONF_VESSEL_WATCHLIST] = ",".join(
        item.strip()
        for item in str(cleaned.get(CONF_VESSEL_WATCHLIST, "")).split(",")
        if item.strip()
    )
    return cleaned


def _home_defaults(hass: Any) -> dict[str, float]:
    """Return a small bounding box centered on the Home Assistant home zone."""
    home = hass.states.get("zone.home")
    attributes = home.attributes if home is not None else {}
    latitude = float(attributes.get("latitude", hass.config.latitude))
    longitude = float(attributes.get("longitude", hass.config.longitude))
    radius = float(attributes.get("radius", hass.config.radius))
    latitude_delta = radius / 111_320
    longitude_delta = radius / (111_320 * max(cos(radians(latitude)), 0.01))
    return {
        CONF_LONGITUDE_WEST: longitude - longitude_delta,
        CONF_LATITUDE_SOUTH: latitude - latitude_delta,
        CONF_LONGITUDE_EAST: longitude + longitude_delta,
        CONF_LATITUDE_NORTH: latitude + latitude_delta,
        CONF_ZONE_RADIUS: radius,
    }


# Kept as compatibility helpers for external tooling and old repair flows.
def _data_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Return the options-compatible common settings schema."""
    return _common_schema(defaults, api_key_required=False, include_area_count=False)


def _validate_input(user_input: dict[str, Any]) -> str | None:
    """Validate common settings for existing callers."""
    return _validate_common_input(user_input)


def _clean_input(user_input: dict[str, Any]) -> dict[str, Any]:
    """Clean common settings for existing callers."""
    return _clean_common_input(user_input)


class _AreaFlowMixin:
    """Implement repeated area steps shared by config and options flows."""

    _pending_settings: dict[str, Any]
    _pending_areas: list[dict[str, Any]]
    _area_count: int
    _area_index: int
    _area_defaults: list[dict[str, Any]]

    async def _async_step_area(self, user_input: dict[str, Any] | None = None):
        """Collect one area and continue until the requested count is reached."""
        errors: dict[str, str] = {}
        defaults = self._area_defaults[self._area_index]
        if user_input is not None:
            error = _validate_area(user_input)
            if error:
                errors["base"] = error
            else:
                self._pending_areas.append(
                    area_from_form(user_input, self._area_index + 1)
                )
                self._area_index += 1
                if self._area_index >= self._area_count:
                    return self._async_finish_area_flow()
                defaults = self._area_defaults[self._area_index]

        return self.async_show_form(
            step_id="area",
            data_schema=_area_schema(defaults),
            description_placeholders={
                "area_number": str(self._area_index + 1),
                "area_count": str(self._area_count),
            },
            errors=errors,
        )


class AisShipTrackerConfigFlow(
    _AreaFlowMixin, config_entries.ConfigFlow, domain=DOMAIN
):
    """Handle a config flow for AIS Ship Tracker."""

    VERSION = 3

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlowWithReload:
        """Return the options flow for an existing config entry."""
        return AisShipTrackerOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial setup step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            area_count = int(user_input.pop(CONF_AREA_COUNT))
            user_input = _clean_common_input(user_input)
            error = _validate_common_input(user_input)
            if error:
                errors["base"] = error
            else:
                await self.async_set_unique_id("ais_ship_tracker")
                self._abort_if_unique_id_configured()
                self._pending_settings = user_input
                self._pending_areas = []
                self._area_count = area_count
                self._area_index = 0
                self._area_defaults = [
                    {CONF_AREA_NAME: "Home", **_home_defaults(self.hass)}
                ] + [{} for _ in range(area_count - 1)]
                return await self._async_step_area()

        return self.async_show_form(
            step_id="user",
            data_schema=_common_schema({CONF_AREA_COUNT: 1}, api_key_required=True),
            errors=errors,
        )

    def _async_finish_area_flow(self):
        """Create the entry after all area forms have been completed."""
        return self.async_create_entry(
            title="AIS Ship Tracker",
            data={**self._pending_settings, CONF_AREAS: self._pending_areas},
        )

    async def async_step_area(self, user_input: dict[str, Any] | None = None):
        """Handle one initial setup area."""
        return await self._async_step_area(user_input)


class AisShipTrackerOptionsFlow(_AreaFlowMixin, OptionsFlowWithReload):
    """Handle options for an existing AIS Ship Tracker entry."""

    def _initialize_pending(self) -> None:
        """Copy current settings into the editable options-flow state."""
        if hasattr(self, "_pending_settings"):
            return
        current = {**self.config_entry.data, **self.config_entry.options}
        self._pending_settings = {
            key: value for key, value in current.items() if key != CONF_AREAS
        }
        self._pending_areas = [dict(area) for area in configured_areas(current)]

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Show the options-flow navigation menu."""
        self._initialize_pending()
        return self.async_show_menu(
            step_id="init", menu_options=["general", "areas", "finish"]
        )

    async def async_step_general(self, user_input: dict[str, Any] | None = None):
        """Manage settings shared by all tracking areas."""
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input = _clean_common_input(user_input)
            if not user_input.get(CONF_API_KEY):
                user_input[CONF_API_KEY] = self._pending_settings.get(
                    CONF_API_KEY, ""
                )
            if not user_input.get(CONF_SEARXNG_PASSWORD):
                user_input.pop(CONF_SEARXNG_PASSWORD, None)
                if self._pending_settings.get(CONF_SEARXNG_PASSWORD):
                    user_input[CONF_SEARXNG_PASSWORD] = self._pending_settings[
                        CONF_SEARXNG_PASSWORD
                    ]
            error = _validate_common_input(user_input)
            if error:
                errors["base"] = error
            else:
                self._pending_settings = user_input
                return await self.async_step_init()

        suggested = dict(self._pending_settings)
        suggested.pop(CONF_API_KEY, None)
        suggested.pop(CONF_SEARXNG_PASSWORD, None)
        return self.async_show_form(
            step_id="general",
            data_schema=self.add_suggested_values_to_schema(
                _common_schema(api_key_required=False, include_area_count=False),
                suggested,
            ),
            errors=errors,
        )

    async def async_step_areas(self, user_input: dict[str, Any] | None = None):
        """Choose an area to edit, remove, or add."""
        self._initialize_pending()
        if user_input is not None:
            action = str(user_input["area_action"])
            if action == "back":
                return await self.async_step_init()
            if action == "add":
                self._area_index = None
                return await self.async_step_area()
            self._area_index = int(action.split(":", 1)[1])
            if action.startswith("remove:"):
                return await self.async_step_remove_area()
            return await self.async_step_area()

        options = [
            {"value": "add", "label": "Add tracking area"},
            *[
                {"value": f"edit:{index}", "label": f"Edit {area['name']}"}
                for index, area in enumerate(self._pending_areas)
            ],
            *[
                {"value": f"remove:{index}", "label": f"Remove {area['name']}"}
                for index, area in enumerate(self._pending_areas)
            ],
            {"value": "back", "label": "Back to settings"},
        ]
        return self.async_show_form(
            step_id="areas",
            data_schema=vol.Schema(
                {
                    vol.Required("area_action"): SelectSelector(
                        SelectSelectorConfig(options=options)
                    )
                }
            ),
        )

    async def async_step_area(self, user_input: dict[str, Any] | None = None):
        """Add or edit one tracking area."""
        errors: dict[str, str] = {}
        is_new = self._area_index is None
        if is_new:
            defaults = {
                CONF_AREA_NAME: f"Area {len(self._pending_areas) + 1}",
                **_home_defaults(self.hass),
            }
        else:
            defaults = area_form_defaults(self._pending_areas[self._area_index])
        if user_input is not None:
            error = _validate_area(user_input)
            if error:
                errors["base"] = error
            else:
                area = area_from_form(
                    user_input,
                    self._area_index + 1
                    if self._area_index is not None
                    else len(self._pending_areas) + 1,
                )
                if is_new:
                    self._pending_areas.append(area)
                else:
                    area["id"] = self._pending_areas[self._area_index].get(
                        "id", area["id"]
                    )
                    self._pending_areas[self._area_index] = area
                return await self.async_step_areas()
        return self.async_show_form(
            step_id="area",
            data_schema=_area_schema(defaults),
            description_placeholders={
                "area_name": str(defaults.get(CONF_AREA_NAME, ""))
            },
            errors=errors,
        )

    async def async_step_remove_area(
        self, user_input: dict[str, Any] | None = None
    ):
        """Confirm removal of one tracking area."""
        errors: dict[str, str] = {}
        area = self._pending_areas[self._area_index]
        if user_input is not None:
            if len(self._pending_areas) == 1:
                errors["base"] = "cannot_remove_last_area"
            elif user_input.get("confirm_remove"):
                self._pending_areas.pop(self._area_index)
                return await self.async_step_areas()
        return self.async_show_form(
            step_id="remove_area",
            data_schema=vol.Schema(
                {vol.Required("confirm_remove", default=False): BooleanSelector()}
            ),
            description_placeholders={"area_name": str(area.get("name", ""))},
            errors=errors,
        )

    async def async_step_finish(self, user_input: dict[str, Any] | None = None):
        """Save the edited settings and areas."""
        del user_input
        return self.async_create_entry(
            title="",
            data={**self._pending_settings, CONF_AREAS: self._pending_areas},
        )
