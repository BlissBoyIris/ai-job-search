"""tools/search_settings.py turns the answers /start saves in my_search.json
into the filters the board tools apply. Pins the friendly failure when the
file is missing, defaults for hand-edited files, and the region rules."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import search_settings  # noqa: E402


def write(data):
    d = tempfile.mkdtemp()
    p = Path(d) / "my_search.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


class TestSearchSettings(unittest.TestCase):
    def test_missing_file_raises_friendly(self):
        with self.assertRaises(search_settings.SettingsMissing) as cm:
            search_settings.load(Path(tempfile.mkdtemp()) / "nope.json")
        self.assertIn("Run /start first", str(cm.exception))

    def test_defaults_fill_missing_keys(self):
        s = search_settings.load(write({"roles": ["designer"]}))
        self.assertEqual(s.work_mode, "remote")
        self.assertEqual(s.max_age_days, 30)
        self.assertIsNone(s.pay_floor_usd_year)
        for wide in ("worldwide", "anywhere", "global"):
            self.assertIn(wide, s.open_to_regions)

    def test_title_patterns(self):
        s = search_settings.load(write({"roles": ["product designer"], "title_skip": ["junior"]}))
        self.assertTrue(s.title_yes().search("Senior Product Designer"))
        self.assertTrue(s.title_no().search("Junior Product Designer"))
        self.assertTrue(s.title_no().search("Design Intern"))
        self.assertFalse(s.title_yes().search("Backend Engineer"))

    def test_region_empty_or_unstated_ok(self):
        s = search_settings.load(write({"roles": ["x"]}))
        self.assertTrue(s.region_ok("")[0])
        self.assertTrue(s.region_ok("", [])[0])

    def test_region_home_country_allowed(self):
        s = search_settings.load(write({"roles": ["x"], "home": {"city": "Nairobi", "country": "Kenya"}}))
        self.assertTrue(s.region_ok("", ["Kenya", "Nigeria"])[0])
        self.assertFalse(s.region_ok("", ["United States"])[0])
        self.assertTrue(s.region_ok("Remote - Kenya")[0])
        self.assertFalse(s.region_ok("Remote - Germany")[0])

    def test_region_skip_unless_wide(self):
        s = search_settings.load(write({"roles": ["x"], "skip_regions": ["brazil"]}))
        self.assertFalse(s.region_ok("Brazil")[0])
        self.assertTrue(s.region_ok("Brazil, Worldwide")[0])

    def test_country_list_needs_exact_region_item(self):
        s = search_settings.load(write({"roles": ["x"], "home": {"country": "Kenya"}, "open_to_regions": ["africa"]}))
        self.assertFalse(s.region_ok("", ["South Africa", "Germany"])[0])
        self.assertTrue(s.region_ok("", ["Africa", "Germany"])[0])
        self.assertTrue(s.region_ok("", ["Worldwide"])[0])

    def test_country_short_names(self):
        us = search_settings.load(write({"roles": ["x"], "home": {"country": "United States"}}))
        for loc in ("USA Only", "Remote - US", "Remote, USA", "U.S."):
            self.assertTrue(us.region_ok(loc)[0], loc)
        self.assertTrue(us.region_ok("", ["USA"])[0])
        uk = search_settings.load(write({"roles": ["x"], "home": {"country": "UK"}}))
        for loc in ("United Kingdom", "Remote, UK", "Great Britain"):
            self.assertTrue(uk.region_ok(loc)[0], loc)
        self.assertFalse(us.region_ok("Remote - UK")[0])

    def test_fully_remote_is_unqualified(self):
        s = search_settings.load(write({"roles": ["x"]}))
        for loc in ("100% Remote", "Fully Remote", "Remote"):
            self.assertTrue(s.region_ok(loc)[0], loc)

    def test_text_region_inside_longer_place_name(self):
        s = search_settings.load(write({"roles": ["x"], "home": {"country": "Kenya"}, "open_to_regions": ["africa"]}))
        self.assertFalse(s.region_ok("Remote (South Africa only)")[0])
        self.assertTrue(s.region_ok("Remote - Africa")[0])
        sd = search_settings.load(write({"roles": ["x"], "home": {"country": "Sudan"}}))
        self.assertFalse(sd.region_ok("South Sudan")[0])

    def test_bad_json_is_friendly(self):
        d = Path(tempfile.mkdtemp()) / "my_search.json"
        d.write_text("{not json", encoding="utf-8")
        with self.assertRaises(search_settings.SettingsMissing) as cm:
            search_settings.load(d)
        self.assertIn("/start", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
