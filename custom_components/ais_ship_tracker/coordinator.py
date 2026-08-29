"""SearXNG search and image-proxy handling for AIS Ship Tracker."""

from __future__ import annotations

import asyncio
import html
import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode, urljoin
from typing import TYPE_CHECKING

from aiohttp import BasicAuth, ClientError, ClientResponseError, ClientSession
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN, ISSUE_SEARXNG_AUTHENTICATION, ISSUE_SEARXNG_ENDPOINT

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .tracker import AisTrackerCoordinator

_MARINE_TRAFFIC_PROXY = re.compile(
    r"/image_proxy\?url=https%3A%2F%2Fwww\.marinetraffic\.com%2FgetAssetDefaultPhoto"
    r"%2F%3Fphoto_size%3D800%26asset_id%3D[0-9]+%26asset_type_id%3D0&h=[0-9a-f]+"
)
_VESSEL_FINDER_PROXY = re.compile(
    r"/image_proxy\?url=https%3A%2F%2Fstatic\.vesselfinder\.net%2Fship-photo%2F[^&\"]+"
    r"&h=[0-9a-f]+"
)
_RETRY_INTERVAL = timedelta(minutes=5)


class ShipPhotoCoordinator:
    """Keep the latest vessel photo and its lookup metadata."""

    def __init__(
        self,
        hass: HomeAssistant,
        session: ClientSession,
        searxng_url: str,
        tracker: AisTrackerCoordinator,
        username: str | None,
        password: str | None,
        entry_id: str,
        area_id: str,
        area_name: str,
    ) -> None:
        self.hass = hass
        self.session = session
        self.searxng_url = searxng_url.rstrip("/")
        self.tracker = tracker
        self.area_id = area_id
        self.area_name = area_name
        self._auth = BasicAuth(username, password) if username else None
        self.entry_id = entry_id
        self._image: bytes | None = None
        self._content_type = "image/jpeg"
        self._mmsi = ""
        self._vessel_name = ""
        self._provider = ""
        self._photo_url = ""
        self._last_attempt: datetime | None = None
        self._last_updated: datetime | None = None
        self._error = ""
        self._listeners: list[Callable[[], None]] = []
        self._lock = asyncio.Lock()

    @property
    def available(self) -> bool:
        """Return whether a current photo is available."""
        return self._image is not None

    @property
    def image(self) -> bytes | None:
        """Return the cached image bytes."""
        return self._image

    @property
    def content_type(self) -> str:
        """Return the cached image content type."""
        return self._content_type

    @property
    def vessel_name(self) -> str:
        """Return the current vessel name."""
        return self._vessel_name

    @property
    def attributes(self) -> dict[str, Any]:
        """Return the current vessel and photo lookup details for the camera."""
        ship = self.tracker.last_ships.get(self.area_id, {})
        ship_attributes = {
            key: value
            for key, value in ship.items()
            if not key.startswith("_") and value is not None
        }
        vessel_name = str(
            ship_attributes.get("ship_name") or self._vessel_name or ""
        )
        mmsi = str(ship_attributes.get("mmsi") or self._mmsi or "")
        search_query = " ".join(part for part in (vessel_name, mmsi) if part)
        search_url = (
            f"{self.searxng_url}/search?"
            f"{urlencode({'q': search_query, 'categories': 'images'})}"
            if self.searxng_url and search_query
            else None
        )
        return {
            **ship_attributes,
            "vessel_name": vessel_name or None,
            "mmsi": mmsi or None,
            "provider": self._provider or None,
            "photo_url": self._photo_url or None,
            "search_query": search_query or None,
            "search_url": search_url,
            "last_updated": self._last_updated.isoformat()
            if self._last_updated
            else None,
            "error": self._error or None,
        }

    @property
    def needs_refresh(self) -> bool:
        """Return whether the current entity needs a lookup."""
        ship = self.tracker.last_ships.get(self.area_id)
        if ship is None:
            return False
        mmsi = str(ship.get("mmsi", ""))
        if mmsi != self._mmsi:
            return True
        return (
            self._last_attempt is None
            or datetime.now(UTC) - self._last_attempt >= _RETRY_INTERVAL
        )

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Register a callback for coordinator updates."""
        self._listeners.append(listener)

        @callback
        def remove_listener() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return remove_listener

    async def async_refresh(self, *, force: bool = False) -> None:
        """Search for and cache the current vessel photo."""
        if not self.searxng_url:
            return
        ship = self.tracker.last_ships.get(self.area_id)
        if ship is None:
            self._set_error("No vessel has been detected yet")
            return

        vessel_name = str(ship.get("ship_name") or "Unknown ship")
        mmsi = str(ship.get("mmsi") or "")
        if not mmsi:
            self._set_error("Tracked vessel has no MMSI")
            return
        if (
            not force
            and mmsi == self._mmsi
            and self._last_attempt is not None
            and datetime.now(UTC) - self._last_attempt < _RETRY_INTERVAL
        ):
            return

        async with self._lock:
            self._last_attempt = datetime.now(UTC)
            self._vessel_name = vessel_name
            self._mmsi = mmsi
            self._provider = ""
            self._photo_url = ""
            self._image = None
            self._error = ""
            query = " ".join(part for part in (vessel_name, mmsi) if part)
            search_url = f"{self.searxng_url}/search?{urlencode({'q': query, 'categories': 'images'})}"

            try:
                async with self.session.get(
                    search_url,
                    headers={
                        "Accept": "text/html",
                        "User-Agent": "Home Assistant AIS ship photo camera",
                    },
                    auth=self._auth,
                    timeout=15,
                ) as response:
                    response.raise_for_status()
                    search_html = html.unescape(await response.text())
                self._set_service_issue(None)

                proxy_path = _MARINE_TRAFFIC_PROXY.search(search_html)
                provider = "MarineTraffic"
                if proxy_path is None:
                    proxy_path = _VESSEL_FINDER_PROXY.search(search_html)
                    provider = "VesselFinder"
                if proxy_path is None:
                    self._set_error("No MarineTraffic or VesselFinder photo found")
                    _LOGGER.debug(
                        "No photo result found for %s (%s)", vessel_name, mmsi
                    )
                    return

                photo_url = urljoin(f"{self.searxng_url}/", proxy_path.group(0))
                async with self.session.get(
                    photo_url,
                    headers={"User-Agent": "Home Assistant AIS ship photo camera"},
                    auth=self._auth,
                    timeout=20,
                ) as response:
                    response.raise_for_status()
                    image = await response.read()
                    content_type = response.headers.get("Content-Type", "image/jpeg")

                if not image:
                    self._set_error("Photo proxy returned an empty image")
                    return
                self._image = image
                self._content_type = content_type.split(";", 1)[0]
                self._provider = provider
                self._photo_url = photo_url
                self._last_updated = datetime.now(UTC)
                _LOGGER.debug(
                    "Updated %s photo for %s (%s) via %s",
                    self.tracker.entry_id,
                    vessel_name,
                    mmsi,
                    provider,
                )
            except ClientResponseError as err:
                if err.status in (401, 403):
                    self._set_service_issue(ISSUE_SEARXNG_AUTHENTICATION)
                elif err.status == 404:
                    self._set_service_issue(ISSUE_SEARXNG_ENDPOINT)
                self._set_error(f"Photo lookup failed with HTTP {err.status}")
                _LOGGER.warning(
                    "AIS Ship Tracker photo lookup failed for %s: HTTP %s",
                    mmsi,
                    err.status,
                )
            except (ClientError, asyncio.TimeoutError) as err:
                self._set_error(f"Photo lookup failed: {err}")
                _LOGGER.warning("AIS ship photo lookup failed for %s: %s", mmsi, err)
            finally:
                self._notify_listeners()

    def _set_error(self, error: str) -> None:
        """Set an error while clearing the old photo."""
        self._image = None
        self._error = error

    def _set_service_issue(self, issue_key: str | None) -> None:
        """Create or clear SearXNG service repairs."""
        issue_keys = (ISSUE_SEARXNG_AUTHENTICATION, ISSUE_SEARXNG_ENDPOINT)
        for known_issue in issue_keys:
            issue_id = f"{known_issue}_{self.entry_id}"
            if known_issue == issue_key:
                ir.async_create_issue(
                    self.hass,
                    DOMAIN,
                    issue_id,
                    data={"entry_id": self.entry_id},
                    is_fixable=True,
                    is_persistent=True,
                    issue_domain=DOMAIN,
                    severity=ir.IssueSeverity.ERROR,
                    translation_key=known_issue,
                )
            else:
                ir.async_delete_issue(self.hass, DOMAIN, issue_id)

    def _notify_listeners(self) -> None:
        """Notify entities that coordinator data changed."""
        for listener in tuple(self._listeners):
            listener()
