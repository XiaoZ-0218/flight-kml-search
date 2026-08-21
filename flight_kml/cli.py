"""Command line workflow: search flight instances, then download one as KML.

Discovery (flight number + date -> instances):
  - opensky: OpenSky flights/all scan. Anonymous covers roughly the last 24h;
    set OPENSKY_CLIENT_ID/SECRET for older dates.
  - csv: ADSBexchange daily arrivals CSV (free, no quota; covers ~2024-07
    onward with gaps near the present).
  - auto (default): opensky when reachable for the date, csv otherwise; if
    opensky finds nothing on a date old enough for the CSV archive, tries csv.

Track (picked instance -> positions):
  - adsb.lol daily trace -> adsbexchange samples trace -> OpenSky tracks/all.

Listing goes to stderr; the saved file path goes to stdout, so agent callers
can chain on it. Nothing is picked automatically unless --pick is given.
"""
import argparse
import datetime
import pathlib
import sys

from . import arrivals, http, ident as ident_mod, kml as kml_mod, traces
from .opensky import OpenSky, find_flights, track_points

# Anonymous OpenSky only serves roughly the last day (empirically ~24-26h).
ANON_HORIZON = 22 * 3600  # safety margin below the observed cutoff
# The CSV archive lags behind the present; don't fall back to it for dates
# younger than this.
CSV_MIN_AGE = 3 * 86400


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


def _parse_clock(text, date):
    """'HH:MM' (on date) or 'YYYY-MM-DD HH:MM', always UTC."""
    text = text.strip()
    for fmt, base in (("%H:%M", date), ("%Y-%m-%d %H:%M", None)):
        try:
            t = datetime.datetime.strptime(text, fmt)
            if base is not None:
                t = t.replace(year=base.year, month=base.month, day=base.day)
            return t.replace(tzinfo=datetime.timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"bad time {text!r}, expected 'HH:MM' or 'YYYY-MM-DD HH:MM'")


def _list_flights(flights):
    _eprint(f"{'#':>2}  {'callsign':<9} {'icao24':<7} {'route':<11} "
            f"{'dep (UTC)':<17} {'arr (UTC)':<17} source")
    for i, f in enumerate(flights, 1):
        route = f"{f.get('dep') or '?'}-{f.get('arr') or '?'}"
        _eprint(
            f"{i:>2}  {f['callsign']:<9} {f['icao24']:<7} {route:<11} "
            f"{_utc(f['firstSeen']).strftime('%m-%d %H:%MZ'):<17} "
            f"{_utc(f['lastSeen']).strftime('%m-%d %H:%MZ'):<17} {f['source']}"
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
        description="Find a flight by number and date and save its track "
                    "as a KML file.",
    )
    parser.add_argument("flight", help="flight number, e.g. UA888 / UAL888 / 3U8735")
    parser.add_argument("date", type=_parse_date, help="flight date, YYYY-MM-DD")
    parser.add_argument("--source", choices=["auto", "opensky", "csv"],
                        default="auto",
                        help="discovery source (default auto: OpenSky for "
                             "recent dates, arrivals CSV for older ones)")
    parser.add_argument("--pad", type=int, default=12, metavar="HOURS",
                        help="OpenSky scan: hours before/after the UTC date "
                             "(default 12, max 48; covers local-timezone "
                             "spillover)")
    parser.add_argument("--utc-from", metavar="TIME",
                        help='OpenSky scan window start: "HH:MM" (on the given '
                             'date) or "YYYY-MM-DD HH:MM", UTC')
    parser.add_argument("--utc-to", metavar="TIME",
                        help='OpenSky scan window end, same format')
    parser.add_argument("--pick", type=int, metavar="N",
                        help="download the Nth listed flight (1-based) as KML")
    parser.add_argument("--out", default=".", help="output directory (default: cwd)")
    parser.add_argument("--name", help="output filename (default: auto)")
    args = parser.parse_args(argv)
    args.date_str = args.date.strftime("%Y-%m-%d")

    if not 0 <= args.pad <= 48:
        _eprint("error: --pad must be between 0 and 48 hours")
        return 2
    if args.name and (args.name in (".", "..")
                      or "/" in args.name or "\\" in args.name):
        _eprint("error: --name must be a plain filename, not a path")
        return 2

    try:
        ident = ident_mod.parse(args.flight)
    except ValueError as exc:
        _eprint(f"error: {exc}")
        return 2

    now = datetime.datetime.now(datetime.timezone.utc)
    if args.date > now:
        _eprint("error: date is in the future")
        return 2

    session = http.make_session()
    client = OpenSky.from_env(session=session)
    now_ts = int(now.timestamp())
    cutoff = now_ts - ANON_HORIZON

    begin = int(args.date.timestamp()) - args.pad * 3600
    end = begin + 86400 + 2 * args.pad * 3600
    try:
        if args.utc_from:
            begin = int(_parse_clock(args.utc_from, args.date).timestamp())
        if args.utc_to:
            end = int(_parse_clock(args.utc_to, args.date).timestamp())
    except ValueError as exc:
        _eprint(f"error: {exc}")
        return 2
    # nothing exists in the future; don't spend quota scanning it
    end = min(end, now_ts)
    if end <= begin:
        _eprint("error: scan window is empty (check --utc-from/--utc-to)")
        return 2

    source = args.source
    if source == "auto":
        source = "opensky" if (client.authenticated or end > cutoff) else "csv"

    _eprint(f"searching {ident.display}"
            + (f" (callsign {ident.icao}{ident.digits})" if ident.icao else
               " (unknown airline prefix, matching any callsign with these "
               "digits)")
            + f" on {args.date_str} [{source}] ...")

    flights = []
    if source == "opensky":
        if not client.authenticated and begin < cutoff:
            if end <= cutoff:
                _eprint(f"error: {args.date_str} ±{args.pad}h is entirely beyond "
                        "anonymous OpenSky's roughly 24-hour history. Set "
                        "OPENSKY_CLIENT_ID / OPENSKY_CLIENT_SECRET, or retry "
                        "with --source csv.")
                return 2
            _eprint(f"note: anonymous access covers roughly the last 24h; "
                    f"skipping the part of the window before "
                    f"{_utc(cutoff).strftime('%Y-%m-%d %H:%M')}Z.")
            begin = cutoff

        def progress(b, e):
            _eprint(f"  window {_utc(b).strftime('%Y-%m-%d %H:%M')}Z .. "
                    f"{_utc(e).strftime('%H:%M')}Z")

        try:
            flights = find_flights(client, ident, begin, end, progress=progress)
        except RuntimeError as exc:  # http.ApiError is a RuntimeError
            _eprint(f"error: {exc}")
            return 2
        if (not flights and args.source == "auto"
                and now.timestamp() - args.date.timestamp() > CSV_MIN_AGE):
            _eprint("no OpenSky hits; trying the arrivals CSV archive ...")
            source = "csv"

    if source == "csv":
        try:
            flights = arrivals.find_flights_csv(session, ident, args.date,
                                                log=_eprint)
        except http.ApiError as exc:
            _eprint(f"error: arrivals CSV unavailable for {args.date_str} "
                    f"(archive covers ~2024-07 onward, with gaps near the "
                    f"present): {exc}")
            return 2

    if not flights:
        _eprint("no matching flights found. Double-check the date and flight "
                "number; for OpenSky try a wider --pad, for the CSV archive "
                "note it is keyed by arrival day (long-haul arrivals may land "
                "the next UTC day — already covered) and has gaps.")
        return 1

    _list_flights(flights)
    if args.pick is None:
        _eprint(f"\n{len(flights)} flight(s). Re-run with --pick N to download "
                "the KML.")
        return 0

    if not 1 <= args.pick <= len(flights):
        _eprint(f"error: --pick must be between 1 and {len(flights)}")
        return 2
    flight = flights[args.pick - 1]

    _eprint(f"fetching track for {flight['callsign']} ({flight['icao24']}) ...")
    points, src_name = None, None
    try:
        points, src_name = traces.get_track_points(session, flight, log=_eprint)
    except LookupError as exc:
        _eprint(f"  {exc}")
    if points is None:
        _eprint("  falling back to OpenSky track ...")
        try:
            track = client.track(flight["icao24"], flight["firstSeen"])
        except http.ApiError as exc:
            if exc.status == 404:
                _eprint("error: no stored track for this flight on any source "
                        "(coverage gap). Try another listed instance.")
                return 3
            _eprint(f"error: {exc}")
            return 2
        points = track_points(track)
        src_name = "opensky"
        if not points:
            _eprint("error: OpenSky track is empty (coverage gap).")
            return 3

    description = kml_mod.describe_flight(ident.display, args.date_str,
                                          flight["callsign"], points, src_name)
    try:
        text = kml_mod.build_kml(points, f"{ident.display} {args.date_str}",
                                 description)
    except ValueError as exc:
        _eprint(f"error: {exc}")
        return 3

    path = _out_path(args, ident, flight)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    _eprint(f"{len(points)} positions from {src_name}, {len(text)} bytes written")
    print(path)
    return 0
