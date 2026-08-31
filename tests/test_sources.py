"""Tests for source parsing that do not require a Home Assistant runtime."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = (
    Path(__file__).parents[1]
    / "custom_components"
    / "ais_ship_tracker"
    / "sources.py"
)
SPEC = importlib.util.spec_from_file_location("ais_ship_tracker_sources", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
sources = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = sources
SPEC.loader.exec_module(sources)


class SourceParserTest(unittest.TestCase):
    """Validate the source boundary and normalized fields."""

    def test_aiscatcher_json_full_position(self) -> None:
        observation = sources.parse_aiscatcher_message(
            {
                "class": "AIS",
                "mmsi": 211234567,
                "type": 1,
                "channel": "A",
                "nmea": ["!AIVDM,1,1,,A,payload*00"],
                "lat": 52.52,
                "lon": 13.31,
                "speed": 8.4,
                "course": 127.2,
                "heading": 126,
                "rxtime": "20260831192345",
            }
        )

        self.assertIsNotNone(observation)
        assert observation is not None
        self.assertEqual(observation.source, "local_mqtt")
        self.assertEqual(observation.mmsi, "211234567")
        self.assertEqual(observation.latitude, 52.52)
        self.assertEqual(observation.speed_knots, 8.4)
        self.assertEqual(observation.raw_nmea, ("!AIVDM,1,1,,A,payload*00",))
        self.assertEqual(observation.source_timestamp.year, 2026)

    def test_invalid_payloads_are_ignored(self) -> None:
        self.assertIsNone(sources.parse_aiscatcher_message("not json"))
        self.assertIsNone(sources.parse_aiscatcher_message({"mmsi": "123"}))
        self.assertIsNone(sources.parse_aiscatcher_message({"mmsi": 123456789.0}))
        observation = sources.parse_aiscatcher_message(
            {"mmsi": "211234567", "nmea": "not-an-array"}
        )
        self.assertIsNotNone(observation)
        assert observation is not None
        self.assertEqual(observation.raw_nmea, ())

    def test_aiscatcher_static_data_is_normalized(self) -> None:
        observation = sources.parse_aiscatcher_message(
            {
                "mmsi": "211234567",
                "type": 5,
                "shipname": "TEST VESSEL",
                "callsign": "DTEST",
                "imo": 1234567,
                "destination": "BERLIN",
            }
        )

        self.assertIsNotNone(observation)
        assert observation is not None
        self.assertEqual(observation.ship_name, "TEST VESSEL")
        self.assertEqual(observation.static_data["destination"], "BERLIN")
        self.assertEqual(observation.static_data["imo_number"], "1234567")

    def test_aisstream_position_is_normalized(self) -> None:
        observation = sources.parse_aisstream_message(
            {
                "MessageType": "PositionReport",
                "MetaData": {"MMSI": 211234567, "ShipName": "TEST VESSEL"},
                "Message": {
                    "PositionReport": {
                        "Latitude": 52.52,
                        "Longitude": 13.31,
                        "Sog": 8.4,
                        "Cog": 127.2,
                        "TrueHeading": 126,
                        "NavigationalStatus": 0,
                    }
                },
            }
        )

        self.assertIsNotNone(observation)
        assert observation is not None
        self.assertEqual(observation.source, "aisstream")
        self.assertEqual(observation.vessel_class, "Class A")
        self.assertEqual(observation.navigational_status, 0)


if __name__ == "__main__":
    unittest.main()
