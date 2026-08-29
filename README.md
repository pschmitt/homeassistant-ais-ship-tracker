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

Create an API key at [AISStream.io](https://aisstream.io). The config flow
first asks for the shared settings and the number of tracking areas. It then
presents one form per area, so multiple areas use the same credentials and a
single AISStream subscription. Each area has a name, south-west and north-east
corners, and its own passive zone radius. Values are decimal degrees; for
example, a small Spree section can be configured as:

```text
West: 13.3125       South: 52.5198
East: 13.3190       North: 52.5235
```

When adding the integration, the first area's coordinates and radius are
initially derived from Home Assistant's `zone.home`. They remain fully
editable in the options flow. Open **Configure** for the integration and use
**Manage tracking areas** to edit a named area, add another, or remove one;
shared settings are edited separately. The integration creates one passive HA
zone per area; the first is `zone.ais_ship_tracking_area` and additional zones include
the configured area name. Additional zones are centered on their bounding box
and have a configurable radius in metres; the first zone follows `zone.home`
exactly. These zones are safe to use on maps without
affecting presence tracking. Zones are updated when the integration is
reconfigured and removed when the integration is removed.

Class B transponders, an MMSI watchlist, and map entity retention can be
changed later from the integration's options. Map entities are limited to ten
active vessels by default; this limit is configurable, and setting it to zero
keeps the shared last-ship entities without creating per-vessel sensors.

SearXNG is optional. If no URL is configured, no photo camera is created. If
configured, the integration searches for the vessel name and MMSI and serves
the selected image through Home Assistant's camera entity.

## Entities

The integration creates these entities unconditionally:

- `sensor.ais_ship_tracker_last_passing_ship` — vessel name, unavailable until
  the first detection or restored state, with AIS data in its attributes.
- `sensor.ais_ship_tracker_ais_connection_status` — diagnostic connection
  state.
- `zone.ais_ship_tracking_area` and one additional passive zone per configured
  area — configurable-radius representations of the target areas for Home
  Assistant map cards.
- `event.ais_ship_tracker_last_ship_updated` — emits `ship_updated` for each
  newly detected MMSI.

When map entities are enabled, up to the configured maximum number of active
vessels get sensors named `sensor.ais_ship_tracker_<ship-name>` with latitude,
longitude, speed, heading, and other AIS attributes. Their unique IDs contain
the MMSI. When a vessel expires from the map
timeout or is evicted by the limit, its entity and entity-registry entry are
removed; it will be recreated if it is observed again.

When SearXNG is configured, the integration additionally creates
`camera.ais_ship_tracker_last_passing_ship_photo`. It includes the provider,
source URL, vessel name, and MMSI as attributes. The dashboard can link to the
vessel's [MarineTraffic page](https://www.marinetraffic.com/).

## License and branding

Copyright © 2026 Philipp Schmitt.

This project is licensed under the GNU General Public License v3.0 or later.
The Home Assistant integration branding is included in
`custom_components/ais_ship_tracker/brand`.
