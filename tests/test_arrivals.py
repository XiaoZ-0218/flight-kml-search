import datetime
import pathlib
import tempfile
import unittest
from unittest import mock

from flight_kml import arrivals, http, ident

COLUMNS = ("key,source,feedtype,callsign,orig,dest,std,schedDep,schedArr,"
           "fpid,gufi,status,type,rules,reg,blocked,hex,beacon,equip,perf,"
           "wake,actype,altitude,speed,route,remarks,clearTime,releaseTime,"
           "taxiTime,depTime,arrTime,parkTime").split(",")


def make_csv(*rows):
    import csv as csv_mod
    import io
    buf = io.StringIO()
    writer = csv_mod.DictWriter(buf, fieldnames=COLUMNS)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


ROW_GOOD = {"callsign": "UAL888", "orig": "KSFO", "dest": "ZBAA",
            "status": "COMPLETED", "hex": "A2F932", "reg": "N26952",
            "depTime": "2026-08-15 17:56:11", "arrTime": "2026-08-16 06:12:03"}
ROW_CANCELLED = {"callsign": "UAL889", "orig": "KSFO", "dest": "ZBAA",
                 "status": "CANCELLED", "hex": "a2f932", "reg": "N26952"}
ROW_OTHER = {"callsign": "AAL100", "orig": "KJFK", "dest": "KLAX",
             "status": "COMPLETED", "hex": "a05764",
             "depTime": "2026-08-15 10:00:00", "arrTime": "2026-08-15 15:00:00"}

DATE = datetime.datetime(2026, 8, 15, tzinfo=datetime.timezone.utc)
# 2026-08-15 17:56:11 UTC
DEP_EPOCH = 1786752000 + 17 * 3600 + 56 * 60 + 11


class TempDir:
    def __enter__(self):
        self._t = tempfile.TemporaryDirectory()
        return pathlib.Path(self._t.name)

    def __exit__(self, *a):
        self._t.cleanup()


class FakeSession:
    pass


def run_with_csv(csv_text, date=DATE):
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as tmp:
        tmp.write(csv_text)
    with mock.patch.object(arrivals, "_csv_path",
                           return_value=pathlib.Path(tmp.name)):
        return arrivals.find_flights_csv(FakeSession(), ident.parse("UA888"),
                                         date)


class FindFlightsCsvTest(unittest.TestCase):
    def test_filters_and_normalizes(self):
        flights = run_with_csv(make_csv(ROW_GOOD, ROW_CANCELLED, ROW_OTHER))
        self.assertEqual(len(flights), 1)
        f = flights[0]
        self.assertEqual(f["icao24"], "a2f932")
        self.assertEqual(f["callsign"], "UAL888")
        self.assertEqual((f["dep"], f["arr"]), ("KSFO", "ZBAA"))
        self.assertEqual(f["firstSeen"], DEP_EPOCH)
        self.assertEqual(f["source"], "adsbx-arrivals")

    def test_no_match(self):
        self.assertEqual(run_with_csv(make_csv(ROW_OTHER)), [])

    def test_no_csv_raises_404(self):
        with mock.patch.object(
            arrivals, "_csv_path",
            side_effect=http.ApiError(404, "u", ""),
        ):
            with self.assertRaises(http.ApiError) as ctx:
                arrivals.find_flights_csv(FakeSession(), ident.parse("UA888"),
                                          DATE)
        self.assertEqual(ctx.exception.status, 404)

    def test_cache_hit_skips_download(self):
        with TempDir() as d:
            (d / "ax_arrivals_20260815.csv").write_text(make_csv(ROW_GOOD))
            with mock.patch.object(arrivals, "_cache_dir", return_value=d), \
                 mock.patch.object(
                     http, "get_bytes",
                     side_effect=http.ApiError(404, "u", "")) as gb:
                flights = arrivals.find_flights_csv(FakeSession(),
                                                    ident.parse("UA888"), DATE)
            self.assertEqual(gb.call_count, 1)  # only day+1 needed downloading
            self.assertEqual(len(flights), 1)

    def test_download_writes_atomically(self):
        # both days serve the same CSV; the duplicate (hex, depTime) dedupes
        with TempDir() as d:
            with mock.patch.object(arrivals, "_cache_dir", return_value=d), \
                 mock.patch.object(http, "get_bytes",
                                   return_value=make_csv(ROW_GOOD).encode()):
                flights = arrivals.find_flights_csv(FakeSession(),
                                                    ident.parse("UA888"), DATE)
            self.assertEqual(len(flights), 1)
            leftover_tmps = [p.name for p in d.iterdir()
                             if p.name.endswith(".tmp")]
            self.assertEqual(leftover_tmps, [])
            self.assertTrue((d / "ax_arrivals_20260815.csv").exists())


if __name__ == "__main__":
    unittest.main()
