"""Native AISStream collector for AIS Ship Tracker."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from math import cos, radians, sqrt
from typing import Any

from aiohttp import WSMsgType
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .areas import area_bounding_box, area_id, area_zone_location, configured_areas
from .const import (CONF_API_KEY, CONF_ENABLE_MAP_ENTITIES,
                    CONF_INCLUDE_CLASS_B, CONF_MAP_TIMEOUT_MINUTES,
                    CONF_MAX_MAP_ENTITIES, CONF_VESSEL_WATCHLIST, DOMAIN,
                    ISSUE_AIS_AUTHENTICATION, ISSUE_AIS_CONNECTION)

_LOGGER = logging.getLogger(__name__)
_AISSTREAM_URL = "wss://stream.aisstream.io/v0/stream"
# Keep the Home Assistant Store version stable. The payload format migration is
# handled below so older installs do not require a Store migration callback.
_STORE_VERSION = 1
_RECONNECT_DELAY = 10

_NAV_STATUS = {
    0: "Under way using engine",
    1: "At anchor",
    2: "Not under command",
    3: "Restricted manoeuvrability",
    4: "Constrained by her draught",
    5: "Moored",
    6: "Aground",
    7: "Engaged in fishing",
    8: "Under way sailing",
    14: "AIS-SART active",
    15: "Not defined",
}

_NAV_ICONS = {
    0: "mdi:ferry",
    1: "mdi:anchor",
    5: "mdi:pier",
    7: "mdi:fish",
    8: "mdi:sail-boat",
}


def _vessel_type(type_number: Any) -> str | None:
    """Return a human-readable AIS vessel type."""
    if not isinstance(type_number, int):
        return None
    ranges = (
        (20, 29, "Wing in ground (WIG)"),
        (30, 30, "Fishing"),
        (31, 32, "Towing"),
        (33, 33, "Dredging"),
        (34, 34, "Diving Ops"),
        (35, 35, "Military Ops"),
        (36, 36, "Sailing"),
        (37, 37, "Pleasure Craft"),
        (40, 49, "High-Speed Craft"),
        (50, 50, "Pilot Vessel"),
        (51, 51, "Search and Rescue"),
        (52, 52, "Tug"),
        (53, 53, "Port Tender"),
        (54, 54, "Anti-pollution Equipment"),
        (55, 55, "Law Enforcement"),
        (60, 69, "Passenger Ship"),
        (70, 79, "Cargo Ship"),
        (80, 89, "Tanker"),
        (90, 99, "Other"),
    )
    for lower, upper, label in ranges:
        if lower <= type_number <= upper:
            return label
    return None


class AisTrackerCoordinator:
    """Own the AISStream connection and the current vessel data."""

    def __init__(
        self, hass: HomeAssistant, session: Any, settings: dict[str, Any], entry_id: str
    ) -> None:
        self.hass = hass
        self.session = session
        self.settings = settings
        self.entry_id = entry_id
        self.last_ships: dict[str, dict[str, Any]] = {}
        self.ship_sightings: dict[str, list[dict[str, str]]] = {}
        self.ships: dict[str, dict[str, Any]] = {}
        self._static_ship_data: dict[str, dict[str, Any]] = {}
        self.connection_status = "Disconnected"
        self.connection_error: str | None = None
        self._seen_mmsis_by_area: dict[str, set[str]] = {}
        self._listeners: list[Callable[[], None]] = []
        self._store = Store(
            hass, _STORE_VERSION, f"{DOMAIN}.last_passing_ship_{entry_id}"
        )
        self._task: asyncio.Task[None] | None = None
        self._stopping = False

    @property
    def last_ship(self) -> dict[str, Any] | None:
        """Return the first area's last ship for backwards compatibility."""
        areas = configured_areas(self.settings)
        if not areas:
            return None
        return self.last_ships.get(area_id(areas[0], 1))

    @property
    def map_entities_enabled(self) -> bool:
        """Return whether individual vessel entities are enabled."""
        return bool(self.settings.get(CONF_ENABLE_MAP_ENTITIES, False))

    @property
    def vessel_watchlist(self) -> list[str]:
        """Return normalized MMSIs configured as a watchlist."""
        raw = str(self.settings.get(CONF_VESSEL_WATCHLIST, ""))
        return [
            item.strip()
            for item in raw.split(",")
            if item.strip().isdigit() and len(item.strip()) == 9
        ]

    @property
    def max_map_entities(self) -> int:
        """Return the maximum number of active vessel entities to expose."""
        return max(0, int(self.settings.get(CONF_MAX_MAP_ENTITIES, 10)))

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Subscribe to coordinator updates."""
        self._listeners.append(listener)

        @callback
        def remove_listener() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return remove_listener

    async def async_start(self) -> None:
        """Restore state and start the AISStream task."""
        self._stopping = False
        stored = await self._store.async_load()
        migrated = False
        if isinstance(stored, dict) and isinstance(stored.get("last_ships"), dict):
            self.last_ships = {
                str(area_key): dict(ship)
                for area_key, ship in stored["last_ships"].items()
                if isinstance(ship, dict) and ship.get("mmsi")
            }
            if isinstance(stored.get("ship_sightings"), dict):
                self.ship_sightings = {
                    str(area_key): [
                        {
                            "mmsi": str(sighting.get("mmsi")),
                            "spotted_time": str(sighting.get("spotted_time")),
                        }
                        for sighting in sightings
                        if isinstance(sighting, dict)
                        and sighting.get("mmsi")
                        and sighting.get("spotted_time")
                    ]
                    for area_key, sightings in stored["ship_sightings"].items()
                    if isinstance(sightings, list)
                }
        elif isinstance(stored, dict) and stored.get("mmsi"):
            # Migrate the original single-area store format to area_1.
            areas = configured_areas(self.settings)
            if areas:
                self.last_ships[area_id(areas[0], 1)] = dict(stored)
                migrated = True
        for area_key, ship in self.last_ships.items():
            self._seen_mmsis_by_area[area_key] = {str(ship["mmsi"])}
            spotted_time = ship.get("spotted_time")
            if not spotted_time:
                continue
            if any(
                sighting.get("mmsi") == str(ship["mmsi"])
                and sighting.get("spotted_time") == str(spotted_time)
                for sighting in self.ship_sightings.get(area_key, [])
            ):
                continue
            self.ship_sightings.setdefault(area_key, []).append(
                {"mmsi": str(ship["mmsi"]), "spotted_time": str(spotted_time)}
            )
            migrated = True
        self._purge_old_sightings()
        if migrated:
            await self._store.async_save(self._stored_data())
        self._purge_old_sightings()
        self._task = self.hass.async_create_task(
            self._run(), name=f"{DOMAIN}_{self.entry_id}"
        )

    async def async_restart(self) -> None:
        """Restart the subscription after a source zone changes."""
        await self.async_stop()
        await self.async_start()

    async def async_stop(self) -> None:
        """Stop the AISStream task."""
        self._stopping = True
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _run(self) -> None:
        """Maintain a reconnecting AISStream websocket."""
        delay = _RECONNECT_DELAY
        while not self._stopping:
            try:
                await self._connect_once()
                delay = _RECONNECT_DELAY
            except asyncio.CancelledError:
                raise
            except Exception as error:  # noqa: BLE001
                self.connection_error = str(error)
                self._set_status("Disconnected")
                _LOGGER.warning("AIS Ship Tracker connection failed: %s", error)
            if not self._stopping:
                await asyncio.sleep(delay)
                delay = min(delay * 2, 120)

    async def _connect_once(self) -> None:
        """Connect once and process AISStream messages until disconnect."""
        self._set_status("Connecting")
        async with self.session.ws_connect(
            _AISSTREAM_URL, heartbeat=30, receive_timeout=90, compress=15
        ) as websocket:
            subscription = {
                "APIKey": self.settings[CONF_API_KEY],
                "BoundingBoxes": [
                    bounding_box
                    for area in configured_areas(self.settings)
                    if (bounding_box := area_bounding_box(self.hass, area)) is not None
                ],
                "FilterMessageTypes": ["PositionReport", "ShipStaticData"],
            }
            if self.settings.get(CONF_INCLUDE_CLASS_B, True):
                subscription["FilterMessageTypes"].extend(
                    ["StandardClassBPositionReport", "ExtendedClassBPositionReport"]
                )
            if self.vessel_watchlist:
                subscription["FiltersShipMMSI"] = self.vessel_watchlist
            await websocket.send_json(subscription)
            confirmed = False
            while not self._stopping:
                try:
                    message = await websocket.receive(timeout=60)
                except asyncio.TimeoutError:
                    self._purge_old_ships()
                    continue
                if message.type in {WSMsgType.TEXT, WSMsgType.BINARY}:
                    payload = (
                        message.data
                        if message.type == WSMsgType.TEXT
                        else message.data.decode("utf-8")
                    )
                    parsed = json.loads(payload)
                    if parsed.get("MessageType") == "SubscriptionConfirmation":
                        confirmed = True
                        self.connection_error = None
                        self._clear_authentication_issue()
                        self._clear_connection_issue()
                        self._set_status("Connected")
                    else:
                        self._handle_message(parsed)
                elif message.type in {
                    WSMsgType.CLOSED,
                    WSMsgType.CLOSING,
                    WSMsgType.CLOSE,
                    WSMsgType.ERROR,
                }:
                    if (
                        not confirmed
                        and self.connection_status != "Authentication failed"
                    ):
                        self._create_connection_issue()
                    raise ConnectionError(
                        "AISStream websocket closed "
                        f"(code={websocket.close_code}, exception={websocket.exception()})"
                    )
                self._purge_old_ships()

    def _handle_message(self, message: dict[str, Any]) -> None:
        """Handle one AISStream message."""
        if message.get("Type") == "Error":
            error = str(message.get("Message", "AISStream returned an error"))
            if any(word in error.lower() for word in ("api key", "unauthor", "auth")):
                self._create_authentication_issue()
                self._set_status("Authentication failed")
            else:
                self._create_connection_issue()
            self.connection_error = error
            _LOGGER.error("AISStream error: %s", error)
            return

        message_type = message.get("MessageType")
        metadata = message.get("MetaData") or {}
        mmsi = str(metadata.get("MMSI") or "")
        if not mmsi:
            return
        if message_type == "ShipStaticData":
            self._handle_static_data(mmsi, message)
            return
        if message_type not in {
            "PositionReport",
            "StandardClassBPositionReport",
            "ExtendedClassBPositionReport",
        }:
            return

        report = (message.get("Message") or {}).get(message_type) or {}
        name = str(metadata.get("ShipName") or "Unknown Ship").strip() or "Unknown Ship"
        nav_status = report.get("NavigationalStatus")
        now = datetime.now(UTC)
        ship = {
            "ship_name": name,
            "mmsi": mmsi,
            "latitude": report.get("Latitude"),
            "longitude": report.get("Longitude"),
            "speed_knots": report.get("Sog"),
            "course": report.get("Cog"),
            "heading": report.get("TrueHeading"),
            "navigational_status": _NAV_STATUS.get(nav_status, "Not defined"),
            "vessel_class": (
                "Class B" if message_type != "PositionReport" else "Class A"
            ),
            "icon": _NAV_ICONS.get(nav_status, "mdi:ferry"),
            "spotted_time": now.isoformat(),
            "_last_seen": now,
        }
        ship.update(self.ships.get(mmsi, {}))
        ship.update(self._static_ship_data.get(mmsi, {}))
        ship["_last_seen"] = now
        self.ships[mmsi] = ship
        self._trim_map_ships()
        stored = False
        public_ship = self._public_ship(ship)
        for tracking_area_id in self._area_ids_for_position(
            report.get("Latitude"), report.get("Longitude")
        ):
            seen_mmsis = self._seen_mmsis_by_area.setdefault(tracking_area_id, set())
            if mmsi in seen_mmsis:
                continue
            seen_mmsis.add(mmsi)
            self.last_ships[tracking_area_id] = public_ship
            self.ship_sightings.setdefault(tracking_area_id, []).append(
                {"mmsi": mmsi, "spotted_time": public_ship["spotted_time"]}
            )
            stored = True
        if stored:
            self._purge_old_sightings()
            self.hass.async_create_task(self._store.async_save(self._stored_data()))
        self._notify()

    def _area_ids_for_position(self, latitude: Any, longitude: Any) -> list[str]:
        """Return tracking areas containing a vessel position."""
        try:
            vessel_latitude = float(latitude)
            vessel_longitude = float(longitude)
        except (TypeError, ValueError):
            return []

        matching_areas = []
        for index, area in enumerate(configured_areas(self.settings), 1):
            location = area_zone_location(self.hass, area)
            if location is None:
                continue
            area_latitude, area_longitude, radius = location
            latitude_distance = (vessel_latitude - area_latitude) * 111_320
            longitude_distance = (
                (vessel_longitude - area_longitude)
                * 111_320
                * cos(radians(area_latitude))
            )
            if sqrt(latitude_distance**2 + longitude_distance**2) <= radius:
                matching_areas.append(area_id(area, index))
        return matching_areas

    def _stored_data(self) -> dict[str, Any]:
        """Return the persisted per-area last-vessel payload."""
        return {
            "last_ships": self.last_ships,
            "ship_sightings": self.ship_sightings,
        }

    def count_ship_sightings(self, area_key: str, *, period: str) -> int:
        """Count distinct MMSIs recorded in the current local time period."""
        now = dt_util.now()
        if period == "day":
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            start = now.replace(minute=0, second=0, microsecond=0)

        mmsis: set[str] = set()
        for sighting in self.ship_sightings.get(area_key, []):
            try:
                spotted = datetime.fromisoformat(sighting["spotted_time"])
            except (KeyError, TypeError, ValueError):
                continue
            if spotted.tzinfo is None:
                spotted = spotted.replace(tzinfo=UTC)
            if start <= dt_util.as_local(spotted) <= now:
                mmsis.add(str(sighting["mmsi"]))
        return len(mmsis)

    def _purge_old_sightings(self) -> None:
        """Keep enough history for current and previous local-day counters."""
        cutoff = datetime.now(UTC) - timedelta(days=2)
        for area_key, sightings in self.ship_sightings.items():
            self.ship_sightings[area_key] = [
                sighting
                for sighting in sightings
                if self._sighting_time(sighting) >= cutoff
            ]

    @staticmethod
    def _sighting_time(sighting: dict[str, str]) -> datetime:
        """Return a sighting timestamp, treating malformed values as expired."""
        try:
            spotted = datetime.fromisoformat(sighting["spotted_time"])
        except (KeyError, TypeError, ValueError):
            return datetime.min.replace(tzinfo=UTC)
        if spotted.tzinfo is None:
            spotted = spotted.replace(tzinfo=UTC)
        return spotted.astimezone(UTC)

    def _trim_map_ships(self) -> None:
        """Keep only the most recently reported vessels for map entities."""
        if not self.map_entities_enabled:
            self.ships.clear()
            return
        excess = len(self.ships) - self.max_map_entities
        if excess <= 0:
            return
        oldest = sorted(
            self.ships,
            key=lambda mmsi: self.ships[mmsi].get(
                "_last_seen", datetime.min.replace(tzinfo=UTC)
            ),
        )[:excess]
        for mmsi in oldest:
            self.ships.pop(mmsi, None)

    def _handle_static_data(self, mmsi: str, message: dict[str, Any]) -> None:
        """Merge static vessel metadata into the tracked vessel."""
        static = (message.get("Message") or {}).get("ShipStaticData") or {}
        eta_data = static.get("Eta") or {}
        eta = None
        if eta_data.get("Month") and eta_data.get("Day"):
            eta = f"{eta_data['Day']:02d}/{eta_data['Month']:02d} {eta_data.get('Hour', 0):02d}:{eta_data.get('Minute', 0):02d} UTC"
        dimensions = static.get("Dimension") or {}
        static_values = {
            "destination": str(static.get("Destination") or "").strip() or None,
            "eta": eta,
            "ship_length": (
                dimensions.get("A", 0) + dimensions.get("B", 0)
                if dimensions.get("A") is not None and dimensions.get("B") is not None
                else None
            ),
            "imo_number": str(static["ImoNumber"]) if static.get("ImoNumber") else None,
            "call_sign": str(static.get("CallSign") or "").strip() or None,
            "vessel_type": _vessel_type(static.get("Type")),
        }
        self._static_ship_data.setdefault(mmsi, {}).update(
            {key: value for key, value in static_values.items() if value is not None}
        )
        ship = self.ships.get(mmsi)
        if ship is not None:
            ship.update(
                {
                    key: value
                    for key, value in static_values.items()
                    if value is not None
                }
            )
            self._notify()
        updated = False
        for last_ship in self.last_ships.values():
            if last_ship.get("mmsi") != mmsi:
                continue
            last_ship.update(
                {
                    key: value
                    for key, value in static_values.items()
                    if value is not None
                }
            )
            updated = True
        if updated:
            self.hass.async_create_task(self._store.async_save(self._stored_data()))
            self._notify()

    def _purge_old_ships(self) -> None:
        """Remove map vessels that have not reported recently."""
        cutoff = datetime.now(UTC) - timedelta(
            minutes=int(self.settings.get(CONF_MAP_TIMEOUT_MINUTES, 30))
        )
        expired = [
            mmsi
            for mmsi, ship in self.ships.items()
            if ship.get("_last_seen", datetime.now(UTC)) < cutoff
        ]
        for mmsi in expired:
            self.ships.pop(mmsi, None)
        if expired:
            self._notify()

    def _public_ship(self, ship: dict[str, Any]) -> dict[str, Any]:
        """Remove internal bookkeeping from a vessel payload."""
        return {
            key: value
            for key, value in ship.items()
            if not key.startswith("_") and value is not None
        }

    @callback
    def _notify(self) -> None:
        for listener in tuple(self._listeners):
            listener()

    @callback
    def _set_status(self, status: str) -> None:
        self.connection_status = status
        self._notify()

    def _create_authentication_issue(self) -> None:
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            f"{ISSUE_AIS_AUTHENTICATION}_{self.entry_id}",
            data={"entry_id": self.entry_id},
            is_fixable=True,
            is_persistent=True,
            issue_domain=DOMAIN,
            severity=ir.IssueSeverity.ERROR,
            translation_key=ISSUE_AIS_AUTHENTICATION,
        )

    def _clear_authentication_issue(self) -> None:
        ir.async_delete_issue(
            self.hass, DOMAIN, f"{ISSUE_AIS_AUTHENTICATION}_{self.entry_id}"
        )

    def _create_connection_issue(self) -> None:
        """Create a repair when AISStream rejects the subscription."""
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            f"{ISSUE_AIS_CONNECTION}_{self.entry_id}",
            data={"entry_id": self.entry_id},
            is_fixable=True,
            is_persistent=True,
            issue_domain=DOMAIN,
            severity=ir.IssueSeverity.ERROR,
            translation_key=ISSUE_AIS_CONNECTION,
        )

    def _clear_connection_issue(self) -> None:
        """Clear the subscription repair after confirmation."""
        ir.async_delete_issue(
            self.hass, DOMAIN, f"{ISSUE_AIS_CONNECTION}_{self.entry_id}"
        )
