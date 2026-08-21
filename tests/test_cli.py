import datetime
import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from flight_kml import cli

# Dates are relative to the clock: the CLI routes on "is the date inside the
# anonymous OpenSky horizon", so hardcoded dates would age out of it.
NOW = datetime.datetime.now(datetime.timezone.utc)
RECENT = NOW - datetime.timedelta(days=1)  # inside the ~24h anonymous horizon
OLD = NOW - datetime.timedelta(days=10)    # old enough for the CSV archive
RECENT_STR = RECENT.strftime("%Y-%m-%d")
OLD_STR = OLD.strftime("%Y-%m-%d")

FIRST_SEEN = int(RECENT.replace(hour=0, minute=0, second=0,
                                microsecond=0).timestamp())
FLIGHT = {
    "icao24": "a1b2c3", "callsign": "UAL888", "dep": "KSFO", "arr": "ZBAA",
    "firstSeen": FIRST_SEEN, "lastSeen": FIRST_SEEN + 3600, "source": "opensky",
}
POINTS = [(FIRST_SEEN + i * 100, -122.3 + i * 0.1, 37.6 + i * 0.1,
           i * 1000.0) for i in range(5)]
OPENSKY_TRACK = {
    "callsign": "UAL888",
    "path": [[p[0], p[2], p[1], p[3], 71, False] for p in POINTS],
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
        client.track.return_value = OPENSKY_TRACK
        patchers = [
            mock.patch.object(cli.OpenSky, "from_env", return_value=client),
            mock.patch.object(cli, "find_flights", return_value=[FLIGHT]),
            mock.patch.object(cli.traces, "get_track_points",
                              return_value=(POINTS, "adsb.lol")),
            # default: CSV archive has nothing; individual tests override
            mock.patch.object(cli.arrivals, "find_flights_csv",
                              return_value=[]),
        ]
        for p in patchers:
            p.start()
            self.addCleanup(p.stop)
        self.client = client

    def test_search_lists_without_downloading(self):
        code, out, err = run(["UA888", RECENT_STR])
        self.assertEqual(code, 0)
        self.assertEqual(out, "")  # nothing on stdout without --pick
        self.assertIn("UAL888", err)
        self.assertIn("KSFO-ZBAA", err)
        self.assertIn("--pick", err)

    def test_pick_downloads_kml_from_trace_source(self):
        with mock.patch("pathlib.Path.write_text") as write:
            code, out, err = run(["UA888", RECENT_STR, "--pick", "1"])
        self.assertEqual(code, 0)
        self.client.track.assert_not_called()  # trace source sufficed
        saved = write.call_args[0][0]
        self.assertIn("<gx:coord>", saved)
        self.assertIn("adsb.lol", saved)
        self.assertTrue(out.strip().endswith(
            f"UA888_{RECENT_STR}_0000Z.kml"))

    def test_pick_falls_back_to_opensky_track(self):
        with mock.patch.object(cli.traces, "get_track_points",
                               side_effect=LookupError("no trace")), \
             mock.patch("pathlib.Path.write_text") as write:
            code, out, err = run(["UA888", RECENT_STR, "--pick", "1"])
        self.assertEqual(code, 0)
        self.client.track.assert_called_once_with("a1b2c3", FIRST_SEEN)
        self.assertIn("<gx:coord>", write.call_args[0][0])

    def test_no_track_anywhere(self):
        self.client.track.side_effect = cli.http.ApiError(404, "u", "no track")
        with mock.patch.object(cli.traces, "get_track_points",
                               side_effect=LookupError("no trace")):
            code, _, err = run(["UA888", RECENT_STR, "--pick", "1"])
        self.assertEqual(code, 3)
        self.assertIn("no stored track", err)

    def test_pick_out_of_range(self):
        code, out, err = run(["UA888", RECENT_STR, "--pick", "9"])
        self.assertEqual(code, 2)

    def test_pick_zero_is_an_error_not_a_listing(self):
        code, _, err = run(["UA888", RECENT_STR, "--pick", "0"])
        self.assertEqual(code, 2)
        self.assertIn("--pick", err)

    def test_name_must_be_a_plain_filename(self):
        for bad in ("../escape", "a/b", ".."):
            code, _, err = run(["UA888", RECENT_STR, "--pick", "1",
                                "--name", bad])
            self.assertEqual(code, 2, bad)
            self.assertIn("--name", err)

    def test_pad_out_of_range(self):
        for bad in ("-1", "100"):
            code, _, err = run(["UA888", RECENT_STR, "--pad", bad])
            self.assertEqual(code, 2, bad)
            self.assertIn("--pad", err)

    def test_bad_ident(self):
        code, _, err = run(["888", RECENT_STR])
        self.assertEqual(code, 2)
        self.assertIn("cannot parse", err)

    def test_future_date_rejected(self):
        code, _, err = run(["UA888", "2099-01-01"])
        self.assertEqual(code, 2)
        self.assertIn("future", err)

    def test_no_flights_recent_date(self):
        # recent date: no CSV fallback (archive lags), just report
        with mock.patch.object(cli, "find_flights", return_value=[]):
            code, _, err = run(["UA888", RECENT_STR])
        self.assertEqual(code, 1)
        self.assertIn("no matching flights", err)

    def test_old_date_auto_uses_csv(self):
        with mock.patch.object(cli.arrivals, "find_flights_csv",
                               return_value=[FLIGHT]) as csv_find, \
             mock.patch.object(cli, "find_flights") as os_find:
            code, out, err = run(["UA888", OLD_STR])
        self.assertEqual(code, 0)
        csv_find.assert_called_once()
        os_find.assert_not_called()

    def test_csv_unavailable(self):
        with mock.patch.object(
            cli.arrivals, "find_flights_csv",
            side_effect=cli.http.ApiError(404, "u", ""),
        ):
            code, _, err = run(["UA888", OLD_STR])
        self.assertEqual(code, 2)
        self.assertIn("arrivals CSV unavailable", err)

    def test_utc_range_overrides_pad(self):
        # fixed past date: authenticated mode skips the anonymous-horizon
        # clipping, and the end is before "now" so it isn't clipped either
        self.client.authenticated = True
        with mock.patch.object(cli, "find_flights", return_value=[]) as ff:
            run(["UA888", "2026-08-15", "--utc-from", "17:00",
                 "--utc-to", "2026-08-16 06:00"])
        begin, end = ff.call_args[0][2:4]
        utc = datetime.timezone.utc
        self.assertEqual(begin, int(datetime.datetime(2026, 8, 15, 17, 0,
                                                      tzinfo=utc).timestamp()))
        self.assertEqual(end, int(datetime.datetime(2026, 8, 16, 6, 0,
                                                    tzinfo=utc).timestamp()))

    def test_scan_end_clipped_to_now(self):
        self.client.authenticated = True
        with mock.patch.object(cli, "find_flights", return_value=[]) as ff:
            run(["UA888", NOW.strftime("%Y-%m-%d")])
        begin, end = ff.call_args[0][2:4]
        self.assertLessEqual(end, int(NOW.timestamp()))

    def test_bad_utc_range(self):
        code, _, err = run(["UA888", "2026-08-15", "--utc-from", "20:00",
                            "--utc-to", "18:00"])
        self.assertEqual(code, 2)
        self.assertIn("empty", err)


if __name__ == "__main__":
    unittest.main()
