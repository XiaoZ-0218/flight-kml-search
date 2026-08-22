import gzip
import json
import unittest
from unittest import mock

from flight_kml import http, traces

# day start 2026-08-15 00:00:00 UTC
DAY = 1786752000.0
TRACE_OBJ = {
    "icao": "aa3ae5",
    "timestamp": DAY,
    "trace": [
        [100.0, 37.6, -122.3, "ground", 0, 0, 0],       # before flight
        [1000.0, 38.0, -122.0, 5000, 250, 90, 0],       # in flight
        [2000.0, 39.0, -121.0, 30000, 450, 90, 0],      # in flight
        [None, 40.0, -120.0, 30000, 450, 90, 0],        # broken row: dropped
        [80000.0, 41.0, -119.0, None, 0, 0, 0],         # next day-ish: outside slice
    ],
}
FLIGHT = {"icao24": "aa3ae5", "callsign": "UAL1722", "dep": "KSFO",
          "arr": "KLAX", "firstSeen": int(DAY) + 1100, "lastSeen": int(DAY) + 1900,
          "source": "test"}


class ParseTest(unittest.TestCase):
    def test_parse_offsets_and_units(self):
        points = traces.parse_trace(TRACE_OBJ)
        # broken row dropped
        self.assertEqual(len(points), 4)
        ts, lon, lat, alt_m = points[1]
        self.assertEqual(ts, int(DAY) + 1000)
        self.assertEqual((lat, lon), (38.0, -122.0))
        self.assertAlmostEqual(alt_m, 5000 * 0.3048)
        # "ground" and None altitude stay None (kml.build_kml fills them)
        self.assertIsNone(points[0][3])
        self.assertIsNone(points[3][3])

    def test_parse_empty(self):
        self.assertEqual(traces.parse_trace({"timestamp": DAY, "trace": []}), [])
        self.assertEqual(traces.parse_trace({}), [])


class SliceTest(unittest.TestCase):
    def test_slice_with_padding(self):
        points = traces.parse_trace(TRACE_OBJ)
        sliced = traces.slice_flight(points, FLIGHT["firstSeen"],
                                     FLIGHT["lastSeen"])
        # pad_before=1800 reaches back to include the offset-100 ground row;
        # the offset-80000 row is far outside
        self.assertEqual([p[0] for p in sliced],
                         [int(DAY) + 100, int(DAY) + 1000, int(DAY) + 2000])


class FetchTest(unittest.TestCase):
    def test_fetch_gzip_and_plain(self):
        raw = json.dumps(TRACE_OBJ).encode()
        for body in (raw, gzip.compress(raw)):
            with mock.patch.object(http, "get_bytes", return_value=body):
                points = traces.fetch_trace(mock.Mock(),
                                            traces.SOURCES["adsb.lol"],
                                            traces._day_start(DAY), "aa3ae5")
            self.assertEqual(len(points), 4)

    def test_fetch_404_returns_none(self):
        with mock.patch.object(http, "get_bytes",
                               side_effect=http.ApiError(404, "u", "")):
            self.assertIsNone(
                traces.fetch_trace(mock.Mock(), traces.SOURCES["adsb.lol"],
                                   traces._day_start(DAY), "aa3ae5"))

    def test_get_track_points_failover(self):
        raw = json.dumps(TRACE_OBJ).encode()

        def fake_get_bytes(session, url, **kw):
            if "adsb.lol" in url:
                raise http.ApiError(404, url, "")
            return raw

        with mock.patch.object(http, "get_bytes", side_effect=fake_get_bytes):
            points, name = traces.get_track_points(mock.Mock(), FLIGHT)
        self.assertEqual(name, "adsbexchange-samples")
        self.assertEqual(len(points), 3)

    def test_get_track_points_lookup_error(self):
        with mock.patch.object(http, "get_bytes",
                               side_effect=http.ApiError(404, "u", "")):
            with self.assertRaises(LookupError):
                traces.get_track_points(mock.Mock(), FLIGHT)


if __name__ == "__main__":
    unittest.main()
