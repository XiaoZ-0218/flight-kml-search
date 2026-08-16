import unittest

from flight_kml import ident


class ParseTest(unittest.TestCase):
    def test_iata_known(self):
        p = ident.parse("UA888")
        self.assertEqual(p.icao, "UAL")
        self.assertEqual(p.digits, "888")

    def test_lowercase_and_spaces(self):
        p = ident.parse("ua 888")
        self.assertEqual(p.icao, "UAL")

    def test_chinese_numeric_prefix(self):
        p = ident.parse("3U8735")
        self.assertEqual(p.icao, "CSC")
        self.assertEqual(p.digits, "8735")

    def test_icao_passthrough(self):
        p = ident.parse("UAL888")
        self.assertEqual(p.icao, "UAL")

    def test_unknown_prefix(self):
        p = ident.parse("ZZ123")
        self.assertIsNone(p.icao)
        self.assertEqual(p.digits, "123")

    def test_suffix_letter(self):
        p = ident.parse("CA1501B")
        self.assertEqual(p.digits, "1501B")

    def test_garbage(self):
        for bad in ["", "888", "UAAAA", "UA88888", "UA-88A-1"]:
            with self.assertRaises(ValueError, msg=bad):
                ident.parse(bad)


class MatchTest(unittest.TestCase):
    def test_exact_callsign(self):
        p = ident.parse("UA888")
        self.assertTrue(ident.matches(p, "UAL888  "))
        self.assertFalse(ident.matches(p, "AAL888"))
        self.assertFalse(ident.matches(p, "UAL889"))

    def test_unknown_prefix_matches_any_digits(self):
        p = ident.parse("ZZ123")
        self.assertTrue(ident.matches(p, "ZZA123"))
        self.assertTrue(ident.matches(p, "UAL123"))
        self.assertFalse(ident.matches(p, "UAL124"))

    def test_non_flight_callsigns(self):
        p = ident.parse("UA888")
        for cs in ["N123AB", "", "BLOCKED", "UAL888A9"]:
            self.assertFalse(ident.matches(p, cs), cs)

    def test_suffix_letter_callsign(self):
        p = ident.parse("CA1501B")
        self.assertTrue(ident.matches(p, "CCA1501B"))


if __name__ == "__main__":
    unittest.main()
