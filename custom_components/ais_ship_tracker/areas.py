"""Helpers for normalizing AIS tracking areas."""

from __future__ import annotations

from typing import Any

from .const import (CONF_AREA_NAME, CONF_AREAS, CONF_LATITUDE_NORTH,
                    CONF_LATITUDE_SOUTH, CONF_LONGITUDE_EAST,
                    CONF_LONGITUDE_WEST, CONF_ZONE_RADIUS)

DEFAULT_AREA_NAME = "Home"


def legacy_area(settings: dict[str, Any]) -> dict[str, Any]:
    """Convert the original single-area settings to one named area."""
    return {
        "id": "area_1",
        "name": DEFAULT_AREA_NAME,
        CONF_LONGITUDE_WEST: float(settings.get(CONF_LONGITUDE_WEST, 0)),
        CONF_LATITUDE_SOUTH: float(settings.get(CONF_LATITUDE_SOUTH, 0)),
        CONF_LONGITUDE_EAST: float(settings.get(CONF_LONGITUDE_EAST, 0)),
        CONF_LATITUDE_NORTH: float(settings.get(CONF_LATITUDE_NORTH, 0)),
        CONF_ZONE_RADIUS: float(settings.get(CONF_ZONE_RADIUS, 100)),
    }


def configured_areas(settings: dict[str, Any]) -> list[dict[str, Any]]:
    """Return normalized configured tracking areas."""
    raw_areas = settings.get(CONF_AREAS)
    if not isinstance(raw_areas, list) or not raw_areas:
        return [legacy_area(settings)]

    areas: list[dict[str, Any]] = []
    for index, raw_area in enumerate(raw_areas, start=1):
        if not isinstance(raw_area, dict):
            continue
        area = dict(raw_area)
        area.setdefault("id", f"area_{index}")
        area.setdefault("name", f"Area {index}")
        area.setdefault(CONF_ZONE_RADIUS, 100)
        areas.append(area)
    return areas or [legacy_area(settings)]


def area_form_defaults(area: dict[str, Any]) -> dict[str, Any]:
    """Convert a stored area to config-flow field names."""
    return {
        CONF_AREA_NAME: area.get("name", DEFAULT_AREA_NAME),
        CONF_LONGITUDE_WEST: area.get(CONF_LONGITUDE_WEST, 0),
        CONF_LATITUDE_SOUTH: area.get(CONF_LATITUDE_SOUTH, 0),
        CONF_LONGITUDE_EAST: area.get(CONF_LONGITUDE_EAST, 0),
        CONF_LATITUDE_NORTH: area.get(CONF_LATITUDE_NORTH, 0),
        CONF_ZONE_RADIUS: area.get(CONF_ZONE_RADIUS, 100),
    }


def area_from_form(user_input: dict[str, Any], index: int) -> dict[str, Any]:
    """Convert config-flow fields to a stored area."""
    return {
        "id": f"area_{index}",
        "name": str(user_input[CONF_AREA_NAME]).strip(),
        CONF_LONGITUDE_WEST: float(user_input[CONF_LONGITUDE_WEST]),
        CONF_LATITUDE_SOUTH: float(user_input[CONF_LATITUDE_SOUTH]),
        CONF_LONGITUDE_EAST: float(user_input[CONF_LONGITUDE_EAST]),
        CONF_LATITUDE_NORTH: float(user_input[CONF_LATITUDE_NORTH]),
        CONF_ZONE_RADIUS: float(user_input[CONF_ZONE_RADIUS]),
    }
