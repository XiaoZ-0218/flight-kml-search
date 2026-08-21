import unittest
from unittest import mock

from flight_kml import http, ident
from flight_kml.opensky import (WINDOW, OpenSky, find_flights, track_points,
                                windows)

FLIGHTS = [
    {"icao24": "a1b2c3", "firstSeen": 1000, "lastSeen": 2000,
     "callsign": "UAL888  ", "estDepartureAirport": "KSFO",
     "estArrivalAirport": "ZBAA"},
    {"icao24": "a1b2c3", "firstSeen": 5000, "lastSeen": 6000,
     "callsign": "UAL888  ", "estDepartureAirport": "ZBAA",
     "estArrivalAirport": "KSFO"},
    {"icao24": "deadbe", "firstSeen": 1100, "lastSeen": 2100,
     "callsign": "AAL100  ", "estDepartureAirport": None,
     "estArrivalAirport": None},
]


class WindowsTest(unittest.TestCase):
    def test_splits_into_bounded_chunks(self):
        ws = list(windows(0, 86400))
        self.assertTrue(all(e - b <= WINDOW for b, e in ws))
        self.assertEqual(ws[0][0], 0)
        self.assertEqual(ws[-1][1], 86400)
        # contiguous
        for (_, e1), (b2, _) in zip(ws, ws[1:]):
            self.assertEqual(e1, b2)

    def test_empty_range(self):
        self.assertEqual(list(windows(100, 100)), [])


class TrackPointsTest(unittest.TestCase):
    def test_extracts_sorts_and_keeps_missing_alt(self):
        track = {"path": [[200, 38.0, -122.0, 1000.0, 90, False],
                          [100, 37.0, -123.0, None, 90, False],
                          [300, None, -121.0, 2000.0, 90, False]]}
        pts = track_points(track)
        self.assertEqual([p[0] for p in pts], [100, 200])  # None lat dropped
        self.assertIsNone(pts[0][3])
        self.assertEqual(pts[1][3], 1000.0)


class FindFlightsTest(unittest.TestCase):
    def test_filters_and_dedupes(self):
        client = mock.Mock()
        # same flight shows up in two overlapping windows
        client.flights.side_effect = [FLIGHTS, FLIGHTS[:1]]
        ua888 = ident.parse("UA888")
        found = find_flights(client, ua888, 0, WINDOW + 100)
        self.assertEqual(len(found), 2)
        self.assertEqual([f["firstSeen"] for f in found], [1000, 5000])

    def test_403_raises_with_guidance(self):
        client = mock.Mock()
        client.flights.side_effect = http.ApiError(403, "u", "denied")
        with self.assertRaises(RuntimeError) as ctx:
            find_flights(client, ident.parse("UA888"), 0, 100)
        self.assertIn("OPENSKY_CLIENT_ID", str(ctx.exception))


class RetryTest(unittest.TestCase):
    def test_retries_on_429(self):
        client = OpenSky()
        calls = [http.ApiError(429, "u", "slow down"),
                 http.ApiError(429, "u", "slow down"),
                 [{"icao24": "a1b2c3"}]]
        with mock.patch.object(http, "get_json", side_effect=calls) as gj, \
             mock.patch("time.sleep"):
            result = client.flights(0, 100)
        self.assertEqual(result, [{"icao24": "a1b2c3"}])
        self.assertEqual(gj.call_count, 3)

    def test_gives_up_after_retries(self):
        client = OpenSky()
        with mock.patch.object(
            http, "get_json",
            side_effect=http.ApiError(429, "u", "slow down"),
        ), mock.patch("time.sleep"):
            with self.assertRaises(http.ApiError):
                client.flights(0, 100)


class AuthTest(unittest.TestCase):
    def test_anonymous_by_default(self):
        client = OpenSky()
        self.assertFalse(client.authenticated)
        self.assertIsNone(client._auth_headers())

    def test_token_fetch_and_cache(self):
        client = OpenSky(client_id="id", client_secret="secret")
        tokens = {"access_token": "tok", "expires_in": 600}
        with mock.patch.object(http, "post_form", return_value=tokens) as pf:
            headers1 = client._auth_headers()
            headers2 = client._auth_headers()
        self.assertEqual(pf.call_count, 1)
        self.assertEqual(headers1["Authorization"], "Bearer tok")
        self.assertEqual(headers2["Authorization"], "Bearer tok")
        data = pf.call_args[0][2]
        self.assertEqual(data["grant_type"], "client_credentials")


class UrlPolicyTest(unittest.TestCase):
    def test_rejects_bad_urls(self):
        import requests
        session = requests.Session()
        for url in ["file:///etc/passwd", "http://evil.example.com/x",
                    "gopher://opensky-network.org"]:
            with self.assertRaises(ValueError, msg=url):
                http.get_json(session, url)


if __name__ == "__main__":
    unittest.main()
