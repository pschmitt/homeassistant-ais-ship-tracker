# AIS Ship Tracker for Home Assistant

AIS Ship Tracker is a Home Assistant custom integration for monitoring vessels
inside one or more configurable geographic areas using the live
[AISStream.io](https://aisstream.io) WebSocket service. It runs entirely as a
Home Assistant integration; no Supervisor add-on or separate daemon is needed.

## Features

- Persistent `Last Passing Ship` state, restored after Home Assistant restarts.
- Connection status and an event fired when a new vessel becomes the last seen vessel.
- A bounded set of temporary per-vessel sensors for map cards; expired vessel
  entities are removed from Home Assistant automatically.
- Optional SearXNG image search, preferring MarineTraffic and falling back to
  VesselFinder, exposed as a `camera` entity.
- Config flow and options flow for one shared API key, multiple named tracking
  areas, filters, map retention, and optional photo lookup.
- Repairs for AISStream authentication/subscription and SearXNG configuration failures.
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

Create an API key at [AISStream.io](https://aisstream.io). Each tracking area
uses an existing Home Assistant `zone.*` entity as its source. The zone's
latitude, longitude, and radius are read directly from Home Assistant; the
integration converts that circular zone into the square south-west/north-east
bounding box required by AISStream. This keeps the HA zone as the single source
of truth: changing its center or radius automatically rebuilds the AIS
subscription.

The initial flow asks for shared settings and the number of tracking areas,
then presents one form per area. Multiple areas use the same credentials and a
single AISStream subscription. Open **Configure** for the integration and use
**Manage tracking areas** to select the source zone for each named area, add
another area, or remove one; shared settings are edited separately.

The integration also creates one passive HA zone per configured area for map
display; the first is `zone.ais_ship_tracking_area` and additional zones
include the configured area name. These mirror zones follow their selected
source zone and are updated when that source changes. They are safe to use on
maps without affecting presence tracking, and are removed with the
integration.

Class B transponders, an MMSI watchlist, and map entity retention can be
changed later from the integration's options. Map entities are limited to ten
active vessels by default; this limit is configurable, and setting it to zero
keeps the per-area last-ship entities without creating per-vessel sensors.

SearXNG is optional. If no URL is configured, no photo camera is created. If
configured, the integration searches for the vessel name and MMSI and serves
the selected image through Home Assistant's camera entity.
If the SearXNG endpoint is protected by an external HTTP Basic Auth layer,
configure its optional username and password; these are not SearXNG account
credentials.

## Entities

The integration creates these entities for every configured tracking area:

- `sensor.ais_ship_tracker_<area>_last_passing_ship` — vessel name, unavailable
  until the first detection or restored state, with AIS data in its attributes.
- `event.ais_ship_tracker_<area>_last_ship_updated` — emits `ship_updated` for
  each newly detected MMSI in that area.
- When SearXNG is configured,
  `camera.ais_ship_tracker_<area>_last_passing_ship_photo` — the latest vessel
  photo for that area.
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

Photo cameras include the current vessel's AIS attributes, the photo provider
and source URL, the generated `search_query` and `search_url`, and any lookup
error as camera attributes. The last-passing-ship sensors, temporary per-vessel
sensors, event entities, and photo cameras expose the same
`vessel_finder_url` attribute whenever an MMSI is available. This makes it easy
to link directly to the vessel's [VesselFinder details
page](https://www.vesselfinder.com/). For example, the default `Home` area uses
`sensor.ais_ship_tracker_home_last_passing_ship`.

## License and branding

Copyright © 2026 Philipp Schmitt.

This project is licensed under the GNU General Public License v3.0 or later.
The Home Assistant integration branding is included in
`custom_components/ais_ship_tracker/brand`.
