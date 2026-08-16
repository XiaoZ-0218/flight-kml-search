---
name: flight-kml-search
description: >
  Find a flight by flight number and date on the OpenSky Network and save its
  ADS-B track as a KML file (openable in Google Earth).
  Trigger when the user gives a flight number plus a date and asks for the
  flight's KML, track, trajectory, or route download.
version: 0.1.0
---

# flight-kml-search

Given a flight number (UA888, CA981, 3U8735 …) and a date, find the matching
flight instance(s) on the OpenSky Network and save the actual flown track as a
**KML file** (gx:Track with timestamps + altitudes, plus a LineString fallback;
opens and animates in Google Earth).

This skill is **self-contained**: the full CLI (`main.py` + the `flight_kml`
package) ships inside this skill directory and runs from anywhere via `uv run`.

The CLI searches and lists — it **never picks a flight instance for you** when
several match. Picking is your job (the model's); guidance below.

## Data source and its limits

Everything comes from the free [OpenSky Network](https://opensky-network.org)
REST API (`/flights/all` for discovery, `/tracks/all` for the track). KML is
generated locally from the returned positions.

- **Anonymous (zero config)**: only works for flights within roughly the
  **last 24 hours**, and the anonymous daily quota is small (~one full-day
  scan). 429 responses mean the quota is burned until tomorrow.
- **With free OpenSky credentials** (recommended): set
  `OPENSKY_CLIENT_ID` + `OPENSKY_CLIENT_SECRET` (create a free account at
  opensky-network.org, then create an API client in the account dashboard).
  Authenticated queries get historical access and a much larger daily quota.
- OpenSky coverage is crowd-sourced ADS-B: oceanic/remote legs may have gaps,
  and some flights have no stored track (CLI exits 3 — pick another instance).

## How to run

```bash
uv run "/Users/zhangxiao/.zcode/skills/flight-kml-search/main.py" <FLIGHT> <YYYY-MM-DD> [flags]
```

Requires `uv` (`brew install uv`). PEP 723 inline metadata resolves the single
dependency (`requests`) into uv's cache — no venv or `cd` needed. Without uv:
`pip install requests` into any Python ≥3.9 and run `python3 main.py ...`.

## Agent workflow

Two runs: search → download the instance you picked.

1. **Search** and read the instance list (stderr):

   ```bash
   uv run "/Users/zhangxiao/.zcode/skills/flight-kml-search/main.py" UA888 2026-08-15
   ```

2. **Pick the right instance** (usually only one per day; multiple rows mean
   the number was reused, e.g. return leg or positioning flight — judge by
   route and times against what the user described), then download:

   ```bash
   uv run "/Users/zhangxiao/.zcode/skills/flight-kml-search/main.py" UA888 2026-08-15 --pick 1
   ```

   The saved file's absolute path is printed on **stdout** (last line);
   everything else is stderr. Default output: `./<FLIGHT>_<DATE>_<HHMMZ>.kml`
   in the current directory — use `--out DIR` to place it where the user wants.

### Saving quota when the departure time is roughly known

Each search scans the UTC date ±12h in ~2-hour API windows (~24 requests).
If the user mentions a departure time, narrow the window (UTC!):

```bash
uv run ".../main.py" UA888 2026-08-15 --utc-from 17:00 --utc-to 23:59
```

`--utc-from/--utc-to` accept `HH:MM` (on the given date) or `YYYY-MM-DD HH:MM`.

## How to pick an instance

- Match **route** (`KSFO-ZBAA` style, ICAO codes; `?` = OpenSky couldn't
  estimate the airport) and **first seen** time against the user's description.
- Same number twice in one day is normal (outbound + return). A callsign with
  a letter suffix (`UAL888A`) is usually a ferry/positioning leg.
- "first seen/last seen" are ADS-B coverage times, roughly takeoff to landing.

## Flags

| Flag | Meaning |
| --- | --- |
| `--pick N` | Download the Nth listed flight (1-based) as KML. Without it, only list. |
| `--pad HOURS` | Search this far before/after the UTC date (default 12). |
| `--utc-from T` / `--utc-to T` | Narrow scan window, UTC (`HH:MM` or `YYYY-MM-DD HH:MM`). |
| `--out DIR` | Output directory (default: current directory). |
| `--name STR` | Output filename override. |

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | listed / downloaded OK |
| 1 | no matching flights found |
| 2 | bad input, API error, or date beyond anonymous horizon without credentials |
| 3 | flight found but OpenSky has no stored track (coverage gap) |

## Notes

- Dates older than ~24h **require** `OPENSKY_CLIENT_ID`/`OPENSKY_CLIENT_SECRET`;
  without them the CLI refuses rather than burning quota on 403s.
- If OpenSky has no data for the flight (small airports, blocked aircraft),
  say so and suggest checking FlightAware manually — its tracklog KML needs a
  logged-in browser session, which is why this skill doesn't scrape it.
- Offline tests (stdlib unittest, no network): from this directory run
  `uv run --with requests python -m unittest discover -s tests -t .`
- Development home: the `flights kml search` workspace project; sync changes
  into the skill copies (`~/.zcode/skills/` and `~/.agents/skills/`).
