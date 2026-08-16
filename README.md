# flight-kml-search

Find a flight by flight number + date on the OpenSky Network and save its
ADS-B track as a KML file (Google Earth compatible, animated gx:Track).

## Quick start

```bash
uv run main.py UA888 2026-08-15            # list matching flight instances
uv run main.py UA888 2026-08-15 --pick 1   # save KML, prints file path
```

Anonymous access covers only roughly the last 24 hours and has a small daily
quota. For older dates and regular use, set `OPENSKY_CLIENT_ID` and
`OPENSKY_CLIENT_SECRET` from a free opensky-network.org account (API client in
the account dashboard).

## Layout

- `main.py` — entry point (PEP 723, `uv run` resolves `requests`)
- `flight_kml/cli.py` — argument parsing and search→pick→download workflow
- `flight_kml/opensky.py` — OpenSky REST client (OAuth2, windows, 429 backoff)
- `flight_kml/ident.py` — flight number parsing, IATA→ICAO callsign matching
- `flight_kml/kml.py` — KML generation from track points
- `flight_kml/http.py` — egress policy (https-only, host allowlist, no
  loopback/private/reserved addresses)
- `tests/` — offline tests: `uv run --with requests python -m unittest discover -s tests -t .`

See `SKILL.md` for the agent-facing usage contract (flags, exit codes,
instance-picking guidance).
