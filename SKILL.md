---
name: flight-kml-search
description: >
  Find a flight by flight number and date and save its ADS-B track as a KML
  file (openable in Google Earth), using only free unauthenticated sources.
  Trigger when the user gives a flight number plus a date and asks for the
  flight's KML, track, trajectory, or route download.
version: 0.2.0
---

# flight-kml-search

Given a flight number (UA888, CA981, 3U8735 …) and a date, find the matching
flight instance(s) and save the actual flown track as a **KML file**
(gx:Track with timestamps + altitudes, plus a LineString fallback; opens and
animates in Google Earth).

This skill is **self-contained**: the full CLI (`main.py` + the `flight_kml`
package) ships inside this skill directory and runs from anywhere via `uv run`.

The CLI searches and lists — it **never picks a flight instance for you** when
several match. Picking is your job (the model's); guidance below.

## Sources (all free, no registration needed)

Two steps are involved, each with its own sources and automatic failover:

**Discovery** (flight number + date → aircraft hex + times):

| Source | Coverage | Notes |
| --- | --- | --- |
| `opensky` | last ~24h anonymous; older with free OpenSky credentials | small anonymous daily quota; 429 = burned until tomorrow |
| `csv` | ~2024-07 onward, **gaps near the present** (archive lags by weeks+) | ADSBexchange daily arrivals CSV (~13 MB/day, cached in `~/.cache/flight-kml-search`); keyed by arrival day |

`--source auto` (default) picks: OpenSky when the date is within anonymous
reach or credentials exist, CSV otherwise. If OpenSky finds nothing on a date
old enough for the archive, it falls back to the CSV automatically.

**Track** (hex + times → positions):

| Source | Coverage | Notes |
| --- | --- | --- |
| `adsb.lol` daily trace | ~2023 → yesterday | 5-second resolution, no quota |
| `adsbexchange-samples` | 2016 → ~2024 | archive, same format |
| `opensky` track | recent | fallback; sparser (~10s+) points |

Traces cover the airframe's whole UTC day; the CLI slices out the flight
between its dep/arr times (handling overnight flights across two day files).

Optional but recommended for older dates: set `OPENSKY_CLIENT_ID` +
`OPENSKY_CLIENT_SECRET` (free account at opensky-network.org → API client in
the dashboard). This unlocks OpenSky discovery for any date.

Coverage caveats: ADS-B is crowd-sourced — oceanic/remote legs may have gaps,
mainland-China coverage is thin, and some airframes are blocked entirely
(CLI exits 3; pick another instance or report the gap).

## How to run

```bash
	uv run "/Users/zhangxiao/.agents/skills/flight-kml-search/main.py" <FLIGHT> <YYYY-MM-DD> [flags]
	```

Requires `uv` (`brew install uv`). PEP 723 inline metadata resolves the single
dependency (`requests`) into uv's cache — no venv or `cd` needed. Without uv:
`pip install requests` into any Python ≥3.9 and run `python3 main.py ...`.

## Agent workflow

Two runs: search → download the instance you picked.

1. **Search** and read the instance list (stderr):

   ```bash
   uv run "/Users/zhangxiao/.agents/skills/flight-kml-search/main.py" UA888 2026-08-15
   ```

2. **Pick the right instance** (usually only one per day; multiple rows mean
   the number was reused, e.g. return leg or positioning flight — judge by
   route and times against what the user described), then download:

   ```bash
   uv run "/Users/zhangxiao/.agents/skills/flight-kml-search/main.py" UA888 2026-08-15 --pick 1
   ```

   The saved file's absolute path is printed on **stdout** (last line);
   everything else is stderr. Default output: `./<FLIGHT>_<DATE>_<HHMMZ>.kml`
   in the current directory — use `--out DIR` to place it where the user wants.

### Saving OpenSky quota when the departure time is roughly known

The OpenSky scan covers the UTC date ±12h in ~2-hour windows (~24 requests).
If the user mentions a departure time, narrow the window (UTC!):

```bash
uv run ".../main.py" UA888 2026-08-15 --utc-from 17:00 --utc-to 23:59
```

`--utc-from/--utc-to` accept `HH:MM` (on the given date) or `YYYY-MM-DD HH:MM`.
The CSV source ignores these flags (it reads whole-day files anyway).

## How to pick an instance

- Match **route** (`KSFO-ZBAA` style, ICAO codes; `?` = unknown) and
  **dep/arr times** against the user's description.
- Same number twice in one day is normal (outbound + return). A callsign with
  a letter suffix (`UAL888A`) is usually a ferry/positioning leg.
- CSV times are actual gate-off to gate-on-ish; OpenSky "first/last seen" are
  ADS-B coverage times. Both are UTC.

## Flags

| Flag | Meaning |
| --- | --- |
| `--source auto\|opensky\|csv` | Discovery source (default auto). |
| `--pick N` | Download the Nth listed flight (1-based) as KML. Without it, only list. |
| `--pad HOURS` | OpenSky scan: hours before/after the UTC date (default 12, max 48). |
| `--utc-from T` / `--utc-to T` | Narrow OpenSky scan window, UTC (`HH:MM` or `YYYY-MM-DD HH:MM`). |
| `--out DIR` | Output directory (default: current directory). |
| `--name STR` | Output filename override. |

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | listed / downloaded OK |
| 1 | no matching flights found |
| 2 | bad input, API error, or source unavailable for the date |
| 3 | flight found but no stored track on any source (coverage gap) |

## Notes

- For dates within the last ~24h the OpenSky path is tried first; if the
  anonymous quota is burned (429), wait for the daily reset or set the
  credentials env vars.
- If no source has the flight (small airports, blocked aircraft, very recent
  archive gap), say so and suggest checking FlightAware manually — its
  tracklog KML needs a logged-in browser session, which is why this skill
  doesn't scrape it.
- Offline tests (stdlib unittest, no network): from this directory run
  `uv run --with requests python -m unittest discover -s tests -t .`
- This directory is the skill. Keep the GitHub repo name and the `name:` field
  as `flight-kml-search`.
