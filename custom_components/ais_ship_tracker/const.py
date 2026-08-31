"""Constants for the AIS Ship Tracker integration."""

from __future__ import annotations

DOMAIN = "ais_ship_tracker"
PLATFORMS = ["sensor", "event", "camera"]

CONF_API_KEY = "api_key"
CONF_AISSTREAM_ENABLED = "aisstream_enabled"
CONF_LOCAL_MQTT_ENABLED = "local_mqtt_enabled"
CONF_LOCAL_MQTT_TOPIC = "local_mqtt_topic"
CONF_AISHUB_ENABLED = "aishub_enabled"
CONF_AISHUB_USERNAME = "aishub_username"
CONF_AREAS = "areas"
CONF_AREA_NAME = "area_name"
CONF_AREA_COUNT = "area_count"
CONF_LONGITUDE_WEST = "longitude_west"
CONF_LATITUDE_SOUTH = "latitude_south"
CONF_LONGITUDE_EAST = "longitude_east"
CONF_LATITUDE_NORTH = "latitude_north"
CONF_ENABLE_MAP_ENTITIES = "enable_map_entities"
CONF_MAX_MAP_ENTITIES = "max_map_entities"
CONF_INCLUDE_CLASS_B = "include_class_b"
CONF_VESSEL_WATCHLIST = "vessel_watchlist"
CONF_CLEAR_MAP_ON_STARTUP = "clear_map_on_startup"
CONF_MAP_TIMEOUT_MINUTES = "map_timeout_minutes"
CONF_ZONE_ENTITY = "zone_entity"
CONF_ZONE_RADIUS = "zone_radius"

CONF_SEARXNG_URL = "searxng_url"
CONF_SEARXNG_USERNAME = "searxng_username"
CONF_SEARXNG_PASSWORD = "searxng_password"
CONF_CACHE_PHOTOS = "cache_photos"

ISSUE_SEARXNG_AUTHENTICATION = "searxng_authentication"
ISSUE_SEARXNG_ENDPOINT = "searxng_endpoint"
ISSUE_AIS_AUTHENTICATION = "ais_authentication"
ISSUE_AIS_CONNECTION = "ais_connection"

ZONE_NAME = "AIS Ship Tracking Area"
