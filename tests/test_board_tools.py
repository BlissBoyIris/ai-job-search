"""remote_boards.py and ats_boards.py filter by the user's my_search.json,
not by hardcoded settings. Network calls are never made here: the missing
settings and on-site cases return before fetching."""
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOLS = REPO / "tools"
sys.path.insert(0, str(TOOLS))

import ats_boards  # noqa: E402
import remote_boards  # noqa: E402
import search_settings  # noqa: E402


def settings_file(data):
    p = Path(tempfile.mkdtemp()) / "my_search.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def job(title, annual=None):
    now = datetime.now(timezone.utc)
    return {"title": title, "posted": now, "_region": (True, "ok"), "_annual": annual, "_desc": ""}


class TestKeep(unittest.TestCase):
    def setUp(self):
        self.cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    def test_keep_uses_settings_roles(self):
        designer = search_settings.load(settings_file({"roles": ["product designer"]}))
        accountant = search_settings.load(settings_file({"roles": ["accountant"]}))
        why = remote_boards.Counter()
        self.assertTrue(remote_boards.keep(job("Product Designer"), self.cutoff, why, designer))
        self.assertFalse(remote_boards.keep(job("Product Designer"), self.cutoff, why, accountant))

    def test_keep_pay_floor_optional(self):
        floor = search_settings.load(settings_file({"roles": ["designer"], "pay_floor_usd_year": 30000}))
        none = search_settings.load(settings_file({"roles": ["designer"]}))
        why = remote_boards.Counter()
        self.assertFalse(remote_boards.keep(job("Designer", 20000), self.cutoff, why, floor))
        self.assertTrue(remote_boards.keep(job("Designer", 20000), self.cutoff, why, none))


class TestAtsRegions(unittest.TestCase):
    def test_region_locked_remote_dropped(self):
        us = search_settings.load(settings_file({"roles": ["x"], "home": {"country": "United States"}}))
        ke = search_settings.load(settings_file({"roles": ["x"], "home": {"country": "Kenya"}}))
        for s, loc in ((us, "Remote - India"), (us, "Remote - EMEA"), (ke, "Remote - India"),
                       (ke, "Remote - APAC"), (us, "Remote - China")):
            self.assertFalse(ats_boards.remote_region_ok([loc, "Remote"], s)[0], loc)

    def test_open_remote_kept(self):
        us = search_settings.load(settings_file({"roles": ["x"], "home": {"country": "United States"}}))
        for loc in ("100% Remote", "Fully Remote", "Remote - US", "Remote, USA"):
            self.assertTrue(ats_boards.remote_region_ok([loc, "Remote"], us)[0], loc)


class TestCli(unittest.TestCase):
    def run_tool(self, name, settings):
        out = Path(tempfile.mkdtemp()) / "out.json"
        r = subprocess.run(
            [sys.executable, str(TOOLS / name), "--out", str(out), "--settings", str(settings)],
            capture_output=True, text=True, timeout=30,
        )
        return r, out

    def test_cli_missing_settings_exit_1(self):
        for name in ("remote_boards.py", "ats_boards.py"):
            r, _ = self.run_tool(name, "/nonexistent/my_search.json")
            self.assertEqual(r.returncode, 1, name)
            self.assertIn("Run /start first", r.stderr, name)
            self.assertNotIn("Traceback", r.stderr, name)

    def test_cli_onsite_writes_empty(self):
        s = settings_file({"roles": ["nurse"], "work_mode": "onsite"})
        for name in ("remote_boards.py", "ats_boards.py"):
            r, out = self.run_tool(name, s)
            self.assertEqual(r.returncode, 0, name + r.stderr)
            self.assertEqual(json.loads(out.read_text(encoding="utf-8")), [], name)
            self.assertIn("on-site", r.stdout, name)


class TestGeneric(unittest.TestCase):
    def test_no_hardcoded_filters(self):
        # Titles, regions and pay come only from my_search.json.
        for name in ("remote_boards.py", "ats_boards.py"):
            src = (TOOLS / name).read_text(encoding="utf-8")
            for constant in ("PAY_FLOOR", "LOW_PAY_REGIONS", "GOOD_REGION", "DESC_RESTRICT", "TITLE_YES", "TITLE_NO"):
                self.assertNotIn(constant, src, f"{name} still hardcodes {constant}")


if __name__ == "__main__":
    unittest.main()
