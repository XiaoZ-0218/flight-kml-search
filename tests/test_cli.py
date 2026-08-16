import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from flight_kml import cli

FLIGHT = {
    "icao24": "a1b2c3", "firstSeen": 1786752000, "lastSeen": 1786755600,
    "callsign": "UAL888  ", "estDepartureAirport": "KSFO",
    "estArrivalAirport": "ZBAA",
}
TRACK = {
    "callsign": "UAL888  ",
    "path": [[1786752000 + i * 100, 37.6 + i * 0.1, -122.3 + i * 0.1,
              i * 1000, 71, False] for i in range(5)],
}


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


class CliTest(unittest.TestCase):
    def setUp(self):
        client = mock.Mock()
        client.authenticated = False
        client.track.return_value = TRACK
        patchers = [
            mock.patch.object(cli.OpenSky, "from_env", return_value=client),
            mock.patch.object(cli, "find_flights", return_value=[FLIGHT]),
        ]
        for p in patchers:
            p.start()
            self.addCleanup(p.stop)
        self.client = client

    def test_search_lists_without_downloading(self):
        code, out, err = run(["UA888", "2026-08-15"])
        self.assertEqual(code, 0)
        self.assertEqual(out, "")  # nothing on stdout without --pick
        self.assertIn("UAL888", err)
        self.assertIn("--pick", err)
        self.client.track.assert_not_called()

    def test_pick_downloads_kml(self):
        with mock.patch("pathlib.Path.write_text") as write:
            code, out, err = run(["UA888", "2026-08-15", "--pick", "1"])
        self.assertEqual(code, 0)
        self.client.track.assert_called_once_with("a1b2c3", 1786752000)
        saved = write.call_args[0][0]
        self.assertIn("<gx:coord>", saved)
        self.assertTrue(out.strip().endswith("UA888_2026-08-15_0000Z.kml"))

    def test_pick_out_of_range(self):
        code, out, err = run(["UA888", "2026-08-15", "--pick", "9"])
        self.assertEqual(code, 2)
        self.client.track.assert_not_called()

    def test_bad_ident(self):
        code, _, err = run(["888", "2026-08-15"])
        self.assertEqual(code, 2)
        self.assertIn("cannot parse", err)

    def test_future_date_rejected(self):
        code, _, err = run(["UA888", "2099-01-01"])
        self.assertEqual(code, 2)
        self.assertIn("future", err)

    def test_track_404(self):
        self.client.track.side_effect = cli.http.ApiError(404, "u", "no track")
        code, _, err = run(["UA888", "2026-08-15", "--pick", "1"])
        self.assertEqual(code, 3)
        self.assertIn("no stored track", err)

    def test_no_flights(self):
        with mock.patch.object(cli, "find_flights", return_value=[]):
            code, _, err = run(["UA888", "2026-08-15"])
        self.assertEqual(code, 1)
        self.assertIn("no matching flights", err)

    def test_beyond_anonymous_horizon(self):
        code, _, err = run(["UA888", "2020-01-01"])
        self.assertEqual(code, 2)
        self.assertIn("OPENSKY_CLIENT_ID", err)


if __name__ == "__main__":
    unittest.main()
