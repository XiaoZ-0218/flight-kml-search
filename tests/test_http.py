import socket
import unittest
from unittest import mock

import requests

from flight_kml import http

API_URL = "https://opensky-network.org/api/flights/all"


def public_getaddrinfo(host, port):
    return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("8.8.8.8", 0))]


def fake_response(status=200, text="{}", json_value=None, json_exc=None):
    resp = mock.Mock()
    resp.status_code = status
    resp.text = text
    resp.content = text.encode()
    if json_exc is not None:
        resp.json.side_effect = json_exc
    else:
        resp.json.return_value = {} if json_value is None else json_value
    return resp


class UrlPolicyTest(unittest.TestCase):
    def test_http_scheme_rejected_even_for_allowed_host(self):
        with self.assertRaises(ValueError):
            http.get_json(requests.Session(), "http://opensky-network.org/api")

    def test_unlisted_host_rejected(self):
        with self.assertRaises(ValueError):
            http.get_json(requests.Session(), "https://evil.example.com/x")

    def test_non_public_ips_rejected(self):
        for ip in ("192.168.1.1", "127.0.0.1", "0.0.0.0", "224.0.0.1"):
            with mock.patch("socket.getaddrinfo",
                            return_value=[(socket.AF_INET, 0, 0, "",
                                           (ip, 0))]):
                with self.assertRaises(ValueError, msg=ip):
                    http.get_json(requests.Session(), API_URL)


class RequestBehaviourTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch("socket.getaddrinfo",
                             side_effect=public_getaddrinfo)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_redirects_not_followed(self):
        session = mock.Mock()
        session.get.return_value = fake_response(302, "see elsewhere")
        with self.assertRaises(http.ApiError) as ctx:
            http.get_json(session, API_URL)
        self.assertEqual(ctx.exception.status, 302)
        self.assertFalse(session.get.call_args[1]["allow_redirects"])

    def test_non_json_200_raises_api_error(self):
        session = mock.Mock()
        session.get.return_value = fake_response(
            200, "<html>waf</html>", json_exc=ValueError("no json"))
        with self.assertRaises(http.ApiError) as ctx:
            http.get_json(session, API_URL)
        self.assertIn("non-JSON", str(ctx.exception))

    def test_post_form_rejects_redirects_too(self):
        session = mock.Mock()
        session.post.return_value = fake_response(200, "{}",
                                                  json_value={"ok": 1})
        self.assertEqual(http.post_form(session,
                                        "https://auth.opensky-network.org/t",
                                        {"a": "b"}), {"ok": 1})
        self.assertFalse(session.post.call_args[1]["allow_redirects"])


if __name__ == "__main__":
    unittest.main()
