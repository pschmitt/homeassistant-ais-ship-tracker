"""Config flow for AIS Ship Tracker."""

from __future__ import annotations

from math import cos, radians
from typing import Any
from urllib.parse import urlparse

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, OptionsFlowWithReload
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_API_KEY,
    CONF_ENABLE_MAP_ENTITIES,
    CONF_INCLUDE_CLASS_B,
    CONF_LATITUDE_NORTH,
    CONF_LATITUDE_SOUTH,
    CONF_LONGITUDE_EAST,
    CONF_LONGITUDE_WEST,
    CONF_MAP_TIMEOUT_MINUTES,
    CONF_SEARXNG_PASSWORD,
    CONF_SEARXNG_URL,
    CONF_SEARXNG_USERNAME,
    CONF_VESSEL_WATCHLIST,
    CONF_ZONE_RADIUS,
    DOMAIN,
)


def _valid_url(value: str) -> bool:
    """Return whether a value is an HTTP(S) URL."""
    parsed_url = urlparse(value.strip())
    return parsed_url.scheme in {"http", "https"} and bool(parsed_url.hostname)


def _normalize_url(value: str) -> str:
    """Normalize a configured SearXNG URL."""
    return value.strip().rstrip("/")


def _data_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Return the shared integration settings schema."""
    defaults = defaults or {}
    longitude = NumberSelectorConfig(min=-180, max=180, step=0.001, mode="box")
    latitude = NumberSelectorConfig(min=-90, max=90, step=0.001, mode="box")
    return vol.Schema(
        {
            vol.Required(CONF_API_KEY): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
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
            vol.Required(CONF_ENABLE_MAP_ENTITIES, default=True): BooleanSelector(),
            vol.Required(CONF_INCLUDE_CLASS_B, default=True): BooleanSelector(),
            vol.Optional(CONF_VESSEL_WATCHLIST, default=""): TextSelector(),
            vol.Required(CONF_MAP_TIMEOUT_MINUTES, default=30): NumberSelector(
                NumberSelectorConfig(min=5, max=1440, step=1)
            ),
            vol.Optional(CONF_SEARXNG_URL, default=""): TextSelector(),
            vol.Optional(CONF_SEARXNG_USERNAME): TextSelector(),
            vol.Optional(CONF_SEARXNG_PASSWORD): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
        }
    )


def _validate_input(user_input: dict[str, Any]) -> str | None:
    """Validate settings that selectors cannot express."""
    if not str(user_input.get(CONF_API_KEY, "")).strip():
        return "invalid_api_key"
    if user_input[CONF_LATITUDE_SOUTH] >= user_input[CONF_LATITUDE_NORTH]:
        return "invalid_bounds"
    if user_input[CONF_LONGITUDE_WEST] >= user_input[CONF_LONGITUDE_EAST]:
        return "invalid_bounds"
    if float(user_input.get(CONF_ZONE_RADIUS, 0)) <= 0:
        return "invalid_radius"
    if user_input.get(CONF_SEARXNG_URL) and not _valid_url(
        user_input[CONF_SEARXNG_URL]
    ):
        return "invalid_url"
    return None


def _clean_input(user_input: dict[str, Any]) -> dict[str, Any]:
    """Normalize and remove blank optional secrets."""
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


class AisShipTrackerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for AIS Ship Tracker."""

    VERSION = 2

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlowWithReload:
        """Return the options flow for an existing config entry."""
        return AisShipTrackerOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial setup step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input = _clean_input(user_input)
            error = _validate_input(user_input)
            if error:
                errors["base"] = error
            else:
                await self.async_set_unique_id("ais_ship_tracker")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="AIS Ship Tracker", data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=_data_schema(_home_defaults(self.hass)),
            errors=errors,
        )


class AisShipTrackerOptionsFlow(OptionsFlowWithReload):
    """Handle options for an existing AIS Ship Tracker entry."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Manage AIS Ship Tracker settings."""
        errors: dict[str, str] = {}
        current = {**self.config_entry.data, **self.config_entry.options}
        if user_input is not None:
            user_input = _clean_input(user_input)
            if not user_input.get(CONF_API_KEY):
                user_input[CONF_API_KEY] = current.get(CONF_API_KEY, "")
            if not user_input.get(CONF_SEARXNG_PASSWORD):
                user_input.pop(CONF_SEARXNG_PASSWORD, None)
                if current.get(CONF_SEARXNG_PASSWORD):
                    user_input[CONF_SEARXNG_PASSWORD] = current[CONF_SEARXNG_PASSWORD]
            error = _validate_input(user_input)
            if error:
                errors["base"] = error
            else:
                return self.async_create_entry(title="", data=user_input)

        suggested = dict(current)
        suggested.pop(CONF_SEARXNG_PASSWORD, None)
        suggested.pop(CONF_API_KEY, None)
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(_data_schema(), suggested),
            errors=errors,
        )
