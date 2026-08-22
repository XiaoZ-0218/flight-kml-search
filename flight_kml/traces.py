"""Per-aircraft daily ADS-B traces (readsb "trace_full" format).

Two free, unauthenticated hosts serve the same format:
  - adsb.lol globe_history: roughly 2023 to yesterday, 5-second resolution
  - samples.adsbexchange.com: 2016 to ~2024 (archive no longer updated)

A trace covers the airframe's whole UTC day, so a flight is the slice of
points between its departure and arrival times.

Trace row: [sec_offset_from_day_start, lat, lon, alt_ft|"ground"|None, ...]
Top level: {"timestamp": <unix day start>, "icao": hex, "trace": [rows]}
"""
import datetime
import json

from . import http

SOURCES = {
    "adsb.lol": "https://adsb.lol/globe_history/{y}/{m}/{d}/traces/{xx}/trace_full_{hex}.json",
    "adsbexchange-samples": "https://samples.adsbexchange.com/traces/{y}/{m}/{d}/{xx}/trace_full_{hex}.json",
}

FT_TO_M = 0.3048
# padding around the flight times when slicing the full-day trace
PAD_BEFORE = 1800
PAD_AFTER = 900


def _day_start(ts):
    dt = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc)
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def parse_trace(obj):
    """trace_full JSON -> [(unix_ts, lon, lat, alt_m|None), ...] by time.

    "ground"/missing altitudes stay None; kml.build_kml fills them from
    neighbouring points instead of sinking them to sea level.
    """
    base = obj.get("timestamp")
    rows = obj.get("trace") or []
    if base is None or not rows:
        return []
    points = []
    for row in rows:
        offset, lat, lon = row[0], row[1], row[2]
        if offset is None or lat is None or lon is None:
            continue
        alt = row[3] if len(row) > 3 else None
        if alt is None or alt == "ground":
            alt_m = None
        else:
            alt_m = float(alt) * FT_TO_M
        points.append((int(base + offset), float(lon), float(lat), alt_m))
    points.sort(key=lambda p: p[0])
    return points


def slice_flight(points, first_seen, last_seen,
                 pad_before=PAD_BEFORE, pad_after=PAD_AFTER):
    lo, hi = first_seen - pad_before, last_seen + pad_after
    return [p for p in points if lo <= p[0] <= hi]


def fetch_trace(session, url_pattern, day, icao24):
    """One day's trace for one airframe; None when the host has no file."""
    url = url_pattern.format(
        y=day.strftime("%Y"), m=day.strftime("%m"), d=day.strftime("%d"),
        xx=icao24[-2:], hex=icao24.lower(),
    )
    try:
        body = http.get_bytes(session, url)
    except http.ApiError:
        return None
    try:
        return parse_trace(json.loads(http.gunzip_if_needed(body)))
    except (ValueError, OSError):
        return None


def get_track_points(session, flight, log=None):
    """Try each free trace host in order. Returns (points, source_name).

    flight: normalized dict with icao24, firstSeen, lastSeen.
    Raises LookupError when no host yields a usable slice.
    """
    day0 = _day_start(flight["firstSeen"])
    day1 = _day_start(flight["lastSeen"])
    days = [day0] if day0 == day1 else [day0, day1]
    for name, pattern in SOURCES.items():
        points, missing = [], False
        for day in days:
            day_points = fetch_trace(session, pattern, day, flight["icao24"])
            if day_points is None:
                missing = True
                break
            points.extend(day_points)
        if missing:
            if log:
                log(f"  {name}: no trace for {flight['icao24']} — trying next source")
            continue
        sliced = slice_flight(points, flight["firstSeen"], flight["lastSeen"])
        if len(sliced) >= 2:
            return sliced, name
        if log:
            log(f"  {name}: trace exists but no points within the flight "
                "window — trying next source")
    raise LookupError(f"no trace found for {flight['icao24']} on "
                      f"{day0.strftime('%Y-%m-%d')}")
