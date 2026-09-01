# AIS Ship Tracker for Home Assistant

AIS Ship Tracker is a Home Assistant custom integration for monitoring vessels
inside one or more configurable geographic areas. It can combine the live
[AISStream.io](https://aisstream.io) WebSocket service with locally received
AIS-catcher messages from Home Assistant MQTT. It runs entirely as a Home
Assistant integration; no additional daemon is needed.

## Features

- Persistent `Last Passing Ship` state, restored after Home Assistant restarts.
- Per-area counters for distinct ships detected today and during the rolling
  last 3,600 seconds.
- Connection status and an event fired when a new vessel becomes the last seen vessel.
- A bounded set of temporary per-vessel sensors for map cards; expired vessel
  entities are removed from Home Assistant automatically.
- Vessel photo lookup through optional SearXNG image search plus direct
  VesselFinder and MarineTraffic fallbacks, exposed on the last-vessel sensor,
  with a persistent local photo cache.
- Config flow and options flow for one shared API key, multiple named tracking
  areas, filters, map retention, and optional photo lookup with persistent
  caching.
- Repairs for AISStream authentication/subscription and SearXNG configuration failures.
- Source-aware vessel data: observations record their source, and duplicate
  reports from multiple sources are merged by MMSI.
- Diagnostics with credentials redacted.

## Installation

Install the integration with HACS as a custom repository, or clone this
repository and copy `custom_components/ais_ship_tracker` into Home Assistant's
`custom_components` directory. The repository is named
`homeassistant-ais-ship-tracker` to match the other local Home Assistant
components.

Restart Home Assistant and add **AIS Ship Tracker** from
**Settings → Devices & services → Add integration**.

## Configuration

Create an API key at [AISStream.io](https://aisstream.io) if the AISStream
source is enabled. The local AIS-catcher source can be used by itself. In the
AIS Ship Tracker settings, enable **Local AIS-catcher MQTT source** and enter
the topic configured in the AIS-catcher app (the default is
`ais-catcher/ais`). The integration subscribes through Home Assistant's MQTT
integration; it does not connect to Mosquitto directly.

AISHub is an optional remote source. Enable it under **AISHub source** and
enter the AISHub username/API credential once your contributor account has
been approved. The integration requests only recent positions within the
combined tracking-area bounding box and polls every 65 seconds, respecting
AISHub's one-request-per-minute limit. AISHub access is not available before
the station has been accepted as a contributor; see [AISHub's join
requirements](https://www.aishub.net/join-us).

Each tracking area
uses an existing Home Assistant `zone.*` entity as its source. The zone's
latitude, longitude, and radius are read directly from Home Assistant; the
integration converts that circular zone into the square south-west/north-east
bounding box required by AISStream. This keeps the HA zone as the single source
of truth: changing its center or radius automatically rebuilds the AIS
subscription.

Each area also accepts an optional, larger **extended map radius**. When set,
AIS sources are queried out to that wider radius so more vessels show up on
the map, but the last-passing-ship entity and the today/last-hour sighting
counters still only count vessels inside the area's own zone radius. Leave it
unset to keep detection and the map at the same size. The extended radius
must be at least the zone's own radius.

The initial flow asks for shared settings and the number of tracking areas,
then presents one form per area. Multiple areas use the same credentials and a
single AISStream subscription. Open **Configure** for the integration and use
**Manage tracking areas** to select the source zone for each named area, add
another area, or remove one; shared settings are edited separately.

The integration also creates one passive HA zone for each configured area for
map display; the first is `zone.ais_ship_tracking_area` and additional zones
include the configured area name. These mirror zones follow their selected
source zone and are updated when that source changes. They are safe to use on
maps without affecting presence tracking, and are removed with the
integration.

Class B transponders, an MMSI watchlist, map entity retention, and the maximum
number of map entities can be changed later from the integration's options. Map
entities are limited to ten active vessels by default; this limit is
configurable, and setting it to zero keeps the per-area last-ship entities
without creating per-vessel sensors. A map entity is considered stale when it
has not reported for 30 minutes by default. The `map_timeout_minutes` setting
accepts 5 minutes to 24 hours. Stale entities are removed from both Home
Assistant and the entity registry, and are recreated if the vessel is observed
again. Individual map entities are not restored after a Home Assistant restart.

The per-area `Last Passing Ship` entities are different: they retain the most
recently detected vessel indefinitely and restore it after a restart. They are
replaced when another vessel is detected and removed when the integration or
tracking area is removed.

SearXNG is optional. When configured, the integration searches for the vessel
name and MMSI and attaches the selected image to the last-vessel sensor.
Search results and VesselFinder pages are parsed with Beautiful Soup
rather than relying on fixed HTML attribute ordering. When SearXNG is unset,
unavailable, rate-limited, or returns no supported image result, the integration
still tries the public VesselFinder and then MarineTraffic details pages for a
main vessel photo. The downloaded image is served through a public Home
Assistant endpoint referenced by the sensor's standard `entity_picture`
attribute. This is required because Home Assistant map markers load that URL
as a CSS background image and cannot attach an API bearer token. The endpoint
only serves already-downloaded, publicly sourced vessel photos and does not
expose AIS data or configured credentials.
Downloaded images are always cached by MMSI in Home Assistant storage and
reused after a restart or when that vessel is seen again; without a cached image,
a lookup is retried on startup. Cached entries are retained until the
integration is removed or its storage is cleared.
VesselFinder's generic “No photo” placeholder remains available as the live
sensor image, but is never cached and will be retried like an uncached result.
If the SearXNG endpoint is protected by an external HTTP Basic Auth layer,
configure its optional username and password; these are not SearXNG account
credentials.

## Entities

The integration creates these entities for every configured tracking area:

- `sensor.ais_ship_tracker_<area>_last_passing_ship` — vessel name, unavailable
  until the first detection or restored state, with AIS data in its attributes.
- `sensor.ais_ship_tracker_<area>_ships_today` and
  `sensor.ais_ship_tracker_<area>_ships_this_hour` — distinct MMSI counts for
  the local calendar day and rolling last 3,600 seconds.
- `event.ais_ship_tracker_<area>_last_ship_updated` — emits `ship_updated` for
  each newly detected MMSI in that area after its optional photo lookup
  completes, with a bounded 45-second wait.
- `sensor.ais_ship_tracker_<area>_last_passing_ship` — the latest vessel and,
  when available, its photo through the standard `entity_picture` attribute
  and the matching `picture_url` attribute.
- `sensor.ais_ship_tracker_ais_connection_status` — diagnostic connection
  state.
- `zone.ais_ship_tracking_area` and one additional passive zone per configured
  area — map representations of the selected Home Assistant source zones.

When map entities are enabled, up to the configured maximum number of active
vessels get sensors named `sensor.ais_ship_tracker_<ship-name>` with latitude,
longitude, speed, heading, and other AIS attributes. Their unique IDs contain
the MMSI. When a vessel expires from the map
timeout or is evicted by the limit, its entity and entity-registry entry are
removed; it will be recreated if it is observed again.

When a vessel photo has already been collected, its map sensor also exposes
the standard Home Assistant `entity_picture` attribute and a `picture_url`
attribute. Both point to a Home Assistant endpoint serving the image already
downloaded by the integration, so map rendering does not depend on the
original photo host being reachable from the browser. The endpoint is
intentionally unauthenticated because map marker CSS images cannot attach HA
API credentials. The original provider URL is retained as `photo_source_url`.
Vessels without a collected photo continue to use their AIS icon.

Use the `ais_ship_tracker.refresh_vessel_photo` service to force a fresh
lookup. Target one or more AIS vessel sensors for normal use, provide a
nine-digit `mmsi` for an automation-friendly stable identifier, or leave both
empty to refresh all currently known vessels. The service uses the configured
SearXNG/VesselFinder/MarineTraffic lookup path and never creates synthetic
images. By default a vessel with an already-cached photo is simply restored
from that cache rather than re-fetched; set the service's `ignore_cache`
option to delete the cached photo(s) first and perform a genuinely new
lookup. Combined with leaving the target and MMSI empty, `ignore_cache`
clears the entire photo cache for all configured areas and looks up every
currently known vessel again.

Use the `ais_ship_tracker.purge_vessel_photos` service to delete every
cached vessel photo for all configured areas without looking up new ones —
a plain cache clear, with no automatic resync. Purged vessels get a fresh
photo the next time they become an area's last-passing-ship or a new map
entity is created for them.

The last-passing-ship sensors include the current vessel's AIS attributes, the
photo provider, source URL, photographer, and credit page. The generated
`searxng_search_query` and `searxng_search_url`, plus any lookup error, are
available on the photo lookup diagnostics. The last-passing-ship sensors,
temporary per-vessel sensors, and event entities expose `vessel_finder_url`
whenever an MMSI is available. They also expose
`marinetraffic_url` once a MarineTraffic internal `shipid` has been found in the
SearXNG results. MarineTraffic does not accept an MMSI in that URL position:
the URL must use the form
`https://www.marinetraffic.com/en/ais/details/ships/shipid:<value>`. The
internal ID is retained with the last-ship data, so the link remains available
after a restart. For example, the default `Home` area uses
`sensor.ais_ship_tracker_home_last_passing_ship`.

## Multiple AIS sources

The integration normalizes AISStream and AIS-catcher MQTT messages into the
same vessel model. Configure AIS-catcher MQTT output as `JSON_FULL`: it
contains the decoded position fields required for area tracking. `JSON_NMEA`
contains the raw NMEA sentence and common metadata but not decoded coordinates,
so it cannot by itself create a passing-ship event. Malformed messages and
payloads without a valid nine-digit MMSI are ignored. Position reports update
the vessel and enter the configured area geofence. Static/voyage reports are
retained and merged with later position reports.

The `source` attribute identifies the most recent normalized source ID
(`aisstream`, `local_mqtt`, or `aishub`), while `source_name` provides the
human-readable label (`AISStream`, `AIS-catcher`, or `AISHub`). `sources_seen`
and `sources_seen_names` provide the corresponding lists of all sources that
have reported the vessel during the current runtime. A vessel entering an area
produces one `ship_updated` event even if the same vessel is subsequently
observed through another source.

AISHub positions are marked as `aishub`; they represent the remote aggregate
and are therefore not proof that the local antenna heard a vessel. The local
receiver remains the authoritative source for confirming a ship was actually
received at home. The AIS-catcher app's AISHub UDP output remains available for
sharing this station's raw feed separately from the integration's optional
AISHub inbound source.

aiscatcher.org currently provides the supported upstream community-sharing
path: enable the add-on's **AIS-catcher community sharing** with the UUID from
the site. The site's feeder API is advertised as coming soon, so this release
does not scrape its live map or treat community-map data as local reception.

## License and branding

Copyright © 2026 Philipp Schmitt.

This project is licensed under the GNU General Public License v3.0 or later.
The Home Assistant integration branding is included in
`custom_components/ais_ship_tracker/brand`.
