import unittest
import xml.etree.ElementTree as ET

from flight_kml import kml

KML = "{http://www.opengis.net/kml/2.2}"
GX = "{http://www.google.com/kml/ext/2.2}"

MAX_XML = 1_000_000


def safe_parse(text):
    """ElementTree accepts internal DTD entity expansion; reject such input
    before parsing (we only ever parse our own output here)."""
    assert len(text) <= MAX_XML, "unexpectedly large XML"
    head = text[:4096].upper()
    assert "<!DOCTYPE" not in head and "<!ENTITY" not in head
    return ET.fromstring(text)


POINTS = [
    (1786752000, -122.38, 37.62, 0.0),
    (1786752100, -122.0, 38.0, 457.2),
    (1786752200, -121.5, 38.5, 0.0),
]


class KmlTest(unittest.TestCase):
    def test_valid_kml_with_track(self):
        desc = kml.describe_flight("UA888", "2026-08-15", "UAL888", POINTS,
                                   "adsb.lol")
        text = kml.build_kml(POINTS, "UA888 2026-08-15", desc)
        root = safe_parse(text)
        self.assertEqual(root.tag, KML + "kml")
        track = root.find(f".//{GX}Track")
        whens = track.findall(f"{KML}when")
        coords = track.findall(f"{GX}coord")
        self.assertEqual(len(whens), 3)
        self.assertEqual(len(coords), 3)
        self.assertEqual(whens[0].text, "2026-08-15T00:00:00Z")
        self.assertTrue(coords[1].text.endswith(" 457"))
        # fallback LineString present
        ls = root.find(f".//{KML}LineString/{KML}coordinates")
        self.assertEqual(len(ls.text.split()), 3)

    def test_empty_points_raise(self):
        with self.assertRaises(ValueError):
            kml.build_kml([], "x", "y")

    def test_description_mentions_source(self):
        desc = kml.describe_flight("UA888", "2026-08-15", "UAL888", POINTS,
                                   "adsb.lol")
        self.assertIn("adsb.lol", desc)
        self.assertIn("3 ADS-B positions", desc)


if __name__ == "__main__":
    unittest.main()
