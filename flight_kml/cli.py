"""Command line workflow: search flight instances, then download one as KML.

Listing goes to stderr; the saved file path goes to stdout, so agent callers
can chain on it. Nothing is picked automatically unless --pick is given.
"""
import argparse
import datetime
import pathlib
import sys

from . import http, ident as ident_mod, kml as kml_mod
from .opensky import OpenSky, find_flights


def _eprint(*args):
    print(*args, file=sys.stderr)


def _utc(ts):
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc)


def _parse_date(text):
    try:
        return datetime.datetime.strptime(text, "%Y-%m-%d").replace(
            tzinfo=datetime.timezone.utc
        )
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"bad date {text!r}, expected YYYY-MM-DD"
        )


def _list_flights(flights):
    _eprint(f"{'#':>2}  {'callsign':<9} {'icao24':<7} {'route':<11} "
            f"{'first seen (UTC)':<17} {'last seen (UTC)':<17}")
    for i, f in enumerate(flights, 1):
        route = f"{f.get('estDepartureAirport') or '?'}-{(f.get('estArrivalAirport') or '?')}"
        _eprint(
            f"{i:>2}  {f['callsign'].strip():<9} {f['icao24']:<7} {route:<11} "
            f"{_utc(f['firstSeen']).strftime('%H:%MZ'):<17} "
            f"{_utc(f['lastSeen']).strftime('%H:%MZ'):<17}"
        )


def _out_path(args, ident, flight):
    if args.name:
        filename = args.name if args.name.endswith(".kml") else args.name + ".kml"
    else:
        stamp = _utc(flight["firstSeen"]).strftime("%H%MZ")
        filename = f"{ident.display}_{args.date_str}_{stamp}.kml"
    return pathlib.Path(args.out).expanduser().resolve() / filename


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="flight-kml-search",
        description="Find a flight by number and date on OpenSky and save "
                    "its track as a KML file.",
    )
    parser.add_argument("flight", help="flight number, e.g. UA888 / UAL888 / 3U8735")
    parser.add_argument("date", type=_parse_date, help="flight date, YYYY-MM-DD")
    parser.add_argument("--pad", type=int, default=12, metavar="HOURS",
                        help="search this many hours before/after the UTC date "
                             "(default 12; covers local-timezone spillover)")
    parser.add_argument("--pick", type=int, metavar="N",
                        help="download the Nth listed flight (1-based) as KML")
    parser.add_argument("--out", default=".", help="output directory (default: cwd)")
    parser.add_argument("--name", help="output filename (default: auto)")
    args = parser.parse_args(argv)
    args.date_str = args.date.strftime("%Y-%m-%d")

    try:
        ident = ident_mod.parse(args.flight)
    except ValueError as exc:
        _eprint(f"error: {exc}")
        return 2

    now = datetime.datetime.now(datetime.timezone.utc)
    if args.date > now:
        _eprint("error: date is in the future")
        return 2

    client = OpenSky.from_env()
    # Anonymous OpenSky only serves roughly the last day (empirically ~24-26h).
    ANON_HORIZON = 22 * 3600  # safety margin below the observed cutoff

    begin = int(args.date.timestamp()) - args.pad * 3600
    end = begin + 86400 + 2 * args.pad * 3600
    if not client.authenticated:
        cutoff = int(now.timestamp()) - ANON_HORIZON
        if end <= cutoff:
            _eprint(f"error: {args.date_str} ±{args.pad}h is entirely beyond "
                    "anonymous OpenSky's roughly 24-hour history. Set "
                    "OPENSKY_CLIENT_ID / OPENSKY_CLIENT_SECRET (free account at "
                    "opensky-network.org) to query older dates.")
            return 2
        if begin < cutoff:
            _eprint(f"note: anonymous access covers roughly the last 24h; "
                    f"skipping the part of the window before "
                    f"{_utc(cutoff).strftime('%Y-%m-%d %H:%M')}Z. For older "
                    "dates set OPENSKY_CLIENT_ID / OPENSKY_CLIENT_SECRET.")
            begin = cutoff
    _eprint(f"searching {ident.display}"
            + (f" (callsign {ident.icao}{ident.digits})" if ident.icao else
               " (unknown airline prefix, matching any callsign with these digits)")
            + f" on {args.date_str} ±{args.pad}h ...")

    def progress(b, e):
        _eprint(f"  window {_utc(b).strftime('%Y-%m-%d %H:%M')}Z .. "
                f"{_utc(e).strftime('%H:%M')}Z")

    try:
        flights = find_flights(client, ident, begin, end, progress=progress)
    except (http.ApiError, RuntimeError) as exc:
        _eprint(f"error: {exc}")
        return 2

    if not flights:
        _eprint("no matching flights found. Try a wider --pad, double-check the "
                "date, or (for dates over a week old) configure OpenSky "
                "credentials.")
        return 1

    _list_flights(flights)
    if not args.pick:
        _eprint(f"\n{len(flights)} flight(s). Re-run with --pick N to download "
                "the KML.")
        return 0

    if not 1 <= args.pick <= len(flights):
        _eprint(f"error: --pick must be between 1 and {len(flights)}")
        return 2
    flight = flights[args.pick - 1]

    _eprint(f"fetching track for {flight['callsign'].strip()} "
            f"({flight['icao24']}) ...")
    try:
        track = client.track(flight["icao24"], flight["firstSeen"])
    except http.ApiError as exc:
        if exc.status == 404:
            _eprint("error: OpenSky has no stored track for this flight "
                    "(coverage gap). Try another listed instance.")
            return 3
        _eprint(f"error: {exc}")
        return 2

    try:
        text = kml_mod.kml_from_track(track, ident.display, args.date_str)
    except ValueError as exc:
        _eprint(f"error: {exc}")
        return 3

    path = _out_path(args, ident, flight)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    _eprint(f"{len(text)} bytes written")
    print(path)
    return 0
