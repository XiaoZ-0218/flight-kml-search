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


TRACK = {
    "icao24": "a1b2c3",
    "callsign": "UAL888  ",
    "startTime": 1786752000.0,
    "endTime": 1786755600.0,
    "path": [
        [1786752000, 37.62, -122.38, 0, 71, False],
        [1786752100, 38.0, -122.0, 1500.5, 300, False],
        [1786752200, 38.5, -121.5, None, 300, False],
        [1786752300, None, None, 3000, 300, False],   # gap: dropped
    ],
}


class KmlTest(unittest.TestCase):
    def test_valid_kml_with_track(self):
        text = kml.kml_from_track(TRACK, "UA888", "2026-08-15")
        root = safe_parse(text)
        self.assertEqual(root.tag, KML + "kml")
        track = root.find(f".//{GX}Track")
        whens = track.findall(f"{KML}when")
        coords = track.findall(f"{GX}coord")
        # the None lat/lon point is dropped
        self.assertEqual(len(whens), 3)
        self.assertEqual(len(coords), 3)
        self.assertEqual(whens[0].text, "2026-08-15T00:00:00Z")
        # None altitude becomes 0
        self.assertTrue(coords[2].text.endswith(" 0"))
        # fallback LineString present
        ls = root.find(f".//{KML}LineString/{KML}coordinates")
        self.assertEqual(len(ls.text.split()), 3)

    def test_points_sorted_by_time(self):
        shuffled = dict(TRACK, path=[TRACK["path"][2], TRACK["path"][0],
                                     TRACK["path"][1]])
        points = kml._clean_points(shuffled["path"])
        self.assertEqual([p[0] for p in points],
                         [1786752000, 1786752100, 1786752200])

    def test_empty_path_raises(self):
        with self.assertRaises(ValueError):
            kml.kml_from_track({"path": []}, "UA888", "2026-08-15")

    def test_description_mentions_source(self):
        text = kml.kml_from_track(TRACK, "UA888", "2026-08-15")
        self.assertIn("OpenSky Network", text)


if __name__ == "__main__":
    unittest.main()
