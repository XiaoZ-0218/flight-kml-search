"""OpenSky Network REST client.

Anonymous access covers roughly the last 7 days. Older dates need a free
OpenSky account's OAuth2 client credentials in OPENSKY_CLIENT_ID /
OPENSKY_CLIENT_SECRET.
"""
import os
import time

from . import http
from .ident import matches

API = "https://opensky-network.org/api"
TOKEN_URL = (
    "https://auth.opensky-network.org/auth/realms/opensky-network"
    "/protocol/openid-connect/token"
)
# flights/all rejects intervals larger than 2 hours; stay under.
WINDOW = 6600  # seconds
# polite delay between anonymous requests
ANON_DELAY = 1.2


class OpenSky:
    def __init__(self, session=None, client_id=None, client_secret=None):
        self.session = session or http.make_session()
        self.client_id = client_id
        self.client_secret = client_secret
        self._token = None
        self._token_expiry = 0.0
        self._last_request = 0.0

    @classmethod
    def from_env(cls):
        return cls(
            client_id=os.environ.get("OPENSKY_CLIENT_ID") or None,
            client_secret=os.environ.get("OPENSKY_CLIENT_SECRET") or None,
        )

    @property
    def authenticated(self):
        return bool(self.client_id and self.client_secret)

    def _auth_headers(self):
        if not self.authenticated:
            return None
        now = time.time()
        if not self._token or now >= self._token_expiry - 30:
            data = http.post_form(
                self.session,
                TOKEN_URL,
                {
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
            )
            self._token = data["access_token"]
            self._token_expiry = now + int(data.get("expires_in", 300))
        return {"Authorization": f"Bearer {self._token}"}

    def _get(self, path, params):
        if not self.authenticated:
            wait = ANON_DELAY - (time.time() - self._last_request)
            if wait > 0:
                time.sleep(wait)
        try:
            return http.get_json(
                self.session, API + path, params=params,
                headers=self._auth_headers(),
            )
        finally:
            self._last_request = time.time()

    def flights(self, begin, end):
        """All flights first seen in [begin, end] (unix seconds)."""
        return self._get("/flights/all", {"begin": int(begin), "end": int(end)})

    def track(self, icao24, at_time):
        """Full path of one flight: {icao24, callsign, startTime, endTime,
        path: [[time, lat, lon, baro_alt_m, true_track, on_ground], ...]}"""
        return self._get(
            "/tracks/all", {"icao24": icao24.lower(), "time": int(at_time)}
        )


def windows(begin, end):
    """Split [begin, end] into <=WINDOW-sized chunks."""
    t = begin
    while t < end:
        yield t, min(t + WINDOW, end)
        t += WINDOW


def find_flights(client, ident, begin, end, progress=None):
    """Scan [begin, end] for flights whose callsign matches ident.

    Returns a list of flight dicts, deduplicated by (icao24, firstSeen),
    sorted by firstSeen.
    """
    seen = {}
    for w_begin, w_end in windows(begin, end):
        if progress:
            progress(w_begin, w_end)
        try:
            batch = client.flights(w_begin, w_end)
        except http.ApiError as exc:
            if exc.status == 403:
                raise RuntimeError(
                    "OpenSky refused this time range (403). Anonymous access "
                    "only covers roughly the last day; for older dates set "
                    "OPENSKY_CLIENT_ID and OPENSKY_CLIENT_SECRET from a free "
                    "opensky-network.org account."
                ) from exc
            raise
        for flight in batch or []:
            callsign = (flight.get("callsign") or "").strip()
            if callsign and matches(ident, callsign):
                key = (flight["icao24"], flight["firstSeen"])
                seen[key] = flight
    return sorted(seen.values(), key=lambda f: f["firstSeen"])
