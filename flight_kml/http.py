"""HTTP helpers with a strict egress policy.

Only https to an allowlist of known data hosts is permitted, redirects are
never followed (a 3xx would point outside the allowlist unchecked), and the
resolved address must be a public unicast IP.
"""
import ipaddress
import socket
import urllib.parse

import requests

ALLOWED_HOSTS = frozenset(
    {
        "opensky-network.org",
        "auth.opensky-network.org",
        "adsb.lol",
        "samples.adsbexchange.com",
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
    if parsed.scheme != "https":
        raise ValueError(f"refusing non-https URL: {url}")
    host = parsed.hostname or ""
    if host not in ALLOWED_HOSTS:
        raise ValueError(f"host not allowed: {host}")
    for info in socket.getaddrinfo(host, None):
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_loopback or ip.is_private or ip.is_reserved
                or ip.is_link_local or ip.is_multicast or ip.is_unspecified):
            raise ValueError(f"refusing to contact {host} at {ip}")


def _checked_json(resp, url):
    try:
        return resp.json()
    except ValueError:
        raise ApiError(resp.status_code, url,
                       f"non-JSON response: {resp.text[:100]}") from None


def make_session():
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    return session


def get_json(session, url, params=None, headers=None, timeout=30):
    _check_url(url)
    resp = session.get(url, params=params, headers=headers, timeout=timeout,
                       allow_redirects=False)
    if resp.status_code != 200:
        raise ApiError(resp.status_code, url, resp.text)
    return _checked_json(resp, url)


def post_form(session, url, data, timeout=30):
    _check_url(url)
    resp = session.post(url, data=data, timeout=timeout,
                        allow_redirects=False)
    if resp.status_code != 200:
        raise ApiError(resp.status_code, url, resp.text)
    return _checked_json(resp, url)


def get_bytes(session, url, timeout=60):
    """Raw body; some trace hosts serve gzip without a Content-Encoding
    header, so callers should sniff magic bytes."""
    _check_url(url)
    resp = session.get(url, timeout=timeout, allow_redirects=False)
    if resp.status_code != 200:
        raise ApiError(resp.status_code, url, resp.text[:200])
    return resp.content


def gunzip_if_needed(body):
    if body[:2] == b"\x1f\x8b":
        import gzip

        return gzip.decompress(body)
    return body
