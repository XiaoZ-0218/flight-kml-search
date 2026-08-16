"""HTTP helpers with a strict egress policy.

Only plain http/https to an allowlist of known data hosts is permitted, and
the resolved address must not be loopback / private / reserved.
"""
import ipaddress
import socket
import urllib.parse

import requests

ALLOWED_HOSTS = frozenset(
    {
        "opensky-network.org",
        "auth.opensky-network.org",
    }
)

USER_AGENT = "flight-kml-search/0.1 (+https://opensky-network.org)"


class ApiError(RuntimeError):
    def __init__(self, status, url, body=""):
        self.status = status
        self.url = url
        super().__init__(f"HTTP {status} from {url}: {body[:200]}")


def _check_url(url):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"refusing non-http(s) URL: {url}")
    host = parsed.hostname or ""
    if host not in ALLOWED_HOSTS:
        raise ValueError(f"host not allowed: {host}")
    for info in socket.getaddrinfo(host, None):
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_loopback or ip.is_private or ip.is_reserved or ip.is_link_local:
            raise ValueError(f"refusing to contact {host} at {ip}")


def make_session():
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    return session


def get_json(session, url, params=None, headers=None, timeout=30):
    _check_url(url)
    resp = session.get(url, params=params, headers=headers, timeout=timeout)
    if resp.status_code != 200:
        raise ApiError(resp.status_code, url, resp.text)
    return resp.json()


def post_form(session, url, data, timeout=30):
    _check_url(url)
    resp = session.post(url, data=data, timeout=timeout)
    if resp.status_code != 200:
        raise ApiError(resp.status_code, url, resp.text)
    return resp.json()
