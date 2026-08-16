"""Free historical discovery via ADSBexchange's daily arrivals CSV.

samples.adsbexchange.com publishes flights-ax-v2/YYYY/MM/DD/ax_arrivals_YYYYMMDD.csv
(coverage ~2024-07 onward, with gaps near the present). Each row is one
completed flight with callsign, origin/dest, icao24 hex and actual dep/arr
times, keyed by arrival day — so a flight departing on D is found in the
CSV for D (short haul) or D+1 (long haul / overnight).

Files are ~13 MB; they are cached under ~/.cache/flight-kml-search.
"""
import csv
import datetime
import os
import pathlib

from . import http
from .ident import matches

URL = ("https://samples.adsbexchange.com/flights-ax-v2/"
       "{y}/{m}/{d}/ax_arrivals_{y}{m}{d}.csv")
SOURCE = "adsbx-arrivals"


def _cache_dir():
    base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return pathlib.Path(base) / "flight-kml-search"


def _csv_path(session, day, log=None):
    path = _cache_dir() / f"ax_arrivals_{day.strftime('%Y%m%d')}.csv"
    if path.exists():
        return path
    url = URL.format(y=day.strftime("%Y"), m=day.strftime("%m"),
                     d=day.strftime("%d"))
    if log:
        log(f"  downloading {day.strftime('%Y-%m-%d')} arrivals CSV (~13 MB) ...")
    body = http.get_bytes(session, url, timeout=180)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(http.gunzip_if_needed(body))
    return path


def _parse_time(text):
    return int(datetime.datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
               .replace(tzinfo=datetime.timezone.utc).timestamp())


def _rows(path):
    with open(path, newline="", encoding="utf-8", errors="replace") as fh:
        yield from csv.DictReader(fh)


def find_flights_csv(session, ident, date, log=None):
    """Match ident against arrivals CSVs for date and date+1.

    date: UTC datetime at 00:00. Returns normalized flight dicts sorted by
    departure time. Raises http.ApiError(404) if neither CSV exists.
    """
    days = [date, date + datetime.timedelta(days=1)]
    found, seen, any_csv = [], set(), False
    for day in days:
        try:
            path = _csv_path(session, day, log=log)
        except http.ApiError as exc:
            if log:
                log(f"  arrivals CSV {day.strftime('%Y-%m-%d')}: HTTP "
                    f"{exc.status}")
            continue
        any_csv = True
        for row in _rows(path):
            callsign = (row.get("callsign") or "").strip()
            hexcode = (row.get("hex") or "").strip().lower()
            if not callsign or not hexcode or not matches(ident, callsign):
                continue
            try:
                dep_t, arr_t = _parse_time(row["depTime"]), _parse_time(row["arrTime"])
            except (KeyError, TypeError, ValueError):
                continue  # cancelled or missing actual times
            if (hexcode, dep_t) in seen:
                continue
            seen.add((hexcode, dep_t))
            found.append({
                "icao24": hexcode,
                "callsign": callsign,
                "dep": row.get("orig") or None,
                "arr": row.get("dest") or None,
                "firstSeen": dep_t,
                "lastSeen": arr_t,
                "source": SOURCE,
            })
    if not any_csv:
        raise http.ApiError(404, URL, "no arrivals CSV for these dates")
    found.sort(key=lambda f: f["firstSeen"])
    return found
