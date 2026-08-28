"""Constants for the AIS Ship Tracker integration."""

from __future__ import annotations

DOMAIN = "ais_ship_tracker"
PLATFORMS = ["sensor", "event", "camera"]

CONF_API_KEY = "api_key"
CONF_LONGITUDE_WEST = "longitude_west"
CONF_LATITUDE_SOUTH = "latitude_south"
CONF_LONGITUDE_EAST = "longitude_east"
CONF_LATITUDE_NORTH = "latitude_north"
CONF_ENABLE_MAP_ENTITIES = "enable_map_entities"
CONF_INCLUDE_CLASS_B = "include_class_b"
CONF_VESSEL_WATCHLIST = "vessel_watchlist"
CONF_CLEAR_MAP_ON_STARTUP = "clear_map_on_startup"
CONF_MAP_TIMEOUT_MINUTES = "map_timeout_minutes"

CONF_SEARXNG_URL = "searxng_url"
CONF_SEARXNG_USERNAME = "searxng_username"
CONF_SEARXNG_PASSWORD = "searxng_password"

ISSUE_SEARXNG_AUTHENTICATION = "searxng_authentication"
ISSUE_SEARXNG_ENDPOINT = "searxng_endpoint"
ISSUE_AIS_AUTHENTICATION = "ais_authentication"
