# AIS Ship Tracker for Home Assistant

AIS Ship Tracker is a Home Assistant custom integration for monitoring vessels
inside a configurable geographic bounding box using the live
[AISStream.io](https://aisstream.io) WebSocket service. It runs entirely as a
Home Assistant integration; no Supervisor add-on or separate daemon is needed.

## Features

- Persistent `Last Passing Ship` state, restored after Home Assistant restarts.
- Connection status and an event fired when a new vessel becomes the last seen vessel.
- Optional per-vessel sensors for map cards.
- Optional SearXNG image search, preferring MarineTraffic and falling back to
  VesselFinder, exposed as a `camera` entity.
- Config flow and options flow for the API key, bounding box, filters, map
  retention, and optional photo lookup.
- Repairs for AISStream authentication and SearXNG configuration failures.
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
accepts the south-west and north-east corners of the area to monitor. Values
are decimal degrees; for example, a small Spree section can be configured as:

```text
West: 13.3125       South: 52.5198
East: 13.3190       North: 52.5235
```

Class B transponders, an MMSI watchlist, and map entity retention can be
changed later from the integration's options.

SearXNG is optional. If no URL is configured, no photo camera is created. If
configured, the integration searches for the vessel name and MMSI and serves
the selected image through Home Assistant's camera entity.

## Entities

The integration creates these entities unconditionally:

- `sensor.ais_ship_tracker_last_passing_ship` — vessel name, unavailable until
  the first detection or restored state, with AIS data in its attributes.
- `sensor.ais_ship_tracker_ais_connection_status` — diagnostic connection
  state.
- `event.ais_ship_tracker_last_ship_updated` — emits `ship_updated` for each
  newly detected MMSI.

When map entities are enabled, each active vessel also gets a sensor named
`sensor.ais_ship_<mmsi>` with latitude, longitude, speed, heading, and other
AIS attributes. These entities become unavailable after the configured
timeout and are recreated as needed.

When SearXNG is configured, the integration additionally creates
`camera.ais_ship_tracker_last_passing_ship_photo`. It includes the provider,
source URL, vessel name, and MMSI as attributes. The dashboard can link to the
vessel's [MarineTraffic page](https://www.marinetraffic.com/).

## License and branding

Copyright © 2026 Philipp Schmitt.

This project is licensed under the GNU General Public License v3.0 or later.
The Home Assistant integration branding is included in
`custom_components/ais_ship_tracker/brand`.
