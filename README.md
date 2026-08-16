# flight-kml-search

Find a flight by flight number + date and save its ADS-B track as a KML file
(Google Earth compatible, animated gx:Track). All sources are free and need
no registration.

## Quick start

```bash
uv run main.py UA888 2026-08-15            # list matching flight instances
uv run main.py UA888 2026-08-15 --pick 1   # save KML, prints file path
```

## Sources

**Discovery** (flight number + date → aircraft hex + times), `--source` to override:

- `opensky` — OpenSky Network `flights/all` scan. Anonymous covers roughly the
  last 24h with a small daily quota; set `OPENSKY_CLIENT_ID` /
  `OPENSKY_CLIENT_SECRET` (free account) for older dates.
- `csv` — ADSBexchange daily arrivals CSV (samples.adsbexchange.com), covering
  ~2024-07 onward with gaps near the present. Cached in
  `~/.cache/flight-kml-search`.
- `auto` (default) — OpenSky when in reach, CSV otherwise, with fallback.

**Track** (hex + times → positions), automatic failover:

1. adsb.lol daily trace (~2023 → yesterday, 5 s resolution)
2. samples.adsbexchange.com trace (2016 → ~2024)
3. OpenSky `tracks/all` (recent, sparser)

## Layout

- `main.py` — entry point (PEP 723, `uv run` resolves `requests`)
- `flight_kml/cli.py` — argument parsing and search→pick→download workflow
- `flight_kml/opensky.py` — OpenSky REST client (OAuth2, windows, 429 backoff)
- `flight_kml/arrivals.py` — ADSBexchange arrivals CSV discovery (cached)
- `flight_kml/traces.py` — daily trace fetch/parse/slice with host failover
- `flight_kml/ident.py` — flight number parsing, IATA→ICAO callsign matching
- `flight_kml/kml.py` — KML generation from track points
- `flight_kml/http.py` — egress policy (https-only, host allowlist, no
  loopback/private/reserved addresses)
- `tests/` — offline tests: `uv run --with requests python -m unittest discover -s tests -t .`

See `SKILL.md` for the agent-facing usage contract (flags, exit codes,
instance-picking guidance).
