"""Scripted scrape: hard filters in code, store through scrape_state, posting text cached once."""

import argparse
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import scrape_run  # noqa: E402
import search_settings  # noqa: E402


def hit(**kw):
    base = {"title": "Product Designer", "company": "Acme", "url": "https://jobs.test/1", "location": "Remote",
            "date": "2026-11-20", "description": "", "portal": "freehire-search", "source": "cli"}
    base.update(kw)
    return base


def settings(**raw):
    data = {"roles": ["product designer", "ux designer"], "title_skip": ["junior"], "work_mode": "remote",
            "home": {"city": "Nairobi", "country": "Kenya"}, "skip_regions": ["nigeria"]}
    data.update(raw)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "my_search.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return search_settings.load(path)


class HardFilterTests(unittest.TestCase):
    def setUp(self):
        self.s = settings()

    def keep(self, **kw):
        return scrape_run.hard_filter(hit(**kw), {}, self.s)

    def test_wanted_roles_pass(self):
        for title in ("Product Designer", "Senior UX Designer", "UX Designer (Remote)"):
            with self.subTest(title=title):
                self.assertTrue(self.keep(title=title))

    def test_disqualified_postings_drop(self):
        self.assertFalse(self.keep(title="Senior Backend Engineer"))
        self.assertFalse(self.keep(title="Junior Product Designer"))
        self.assertFalse(self.keep(title="Product Design Intern"))
        self.assertFalse(self.keep(title="Product Designer (Hybrid)"))
        self.assertFalse(self.keep(location="Lagos, Nigeria"))
        self.assertFalse(self.keep(location="Remote - United States"))
        self.assertTrue(self.keep(location="Remote - Kenya"))
        self.assertTrue(self.keep(location="Worldwide"))
        self.assertTrue(self.keep(location="Remote - United States", _regions=["global"]))
        self.assertTrue(self.keep(location="Remote (no region stated)", _region_checked=True))
        self.assertFalse(self.keep(description="Candidates must be based in Nigeria for this role."))

    def test_hybrid_title_kept_when_user_wants_any_mode(self):
        s = settings(work_mode="any")
        self.assertTrue(scrape_run.hard_filter(hit(title="Product Designer (Hybrid)", location="Nairobi, Kenya"), {}, s))


class DefaultQueryTests(unittest.TestCase):
    def test_built_from_roles_and_home(self):
        cfg = scrape_run.default_queries(settings(max_age_days=10))
        self.assertEqual(cfg["freehire"]["queries"], ["title:product designer OR title:ux designer"])
        self.assertIn("--remote", cfg["freehire"]["args"])
        self.assertEqual([r["location"] for r in cfg["linkedin"]["runs"]], ["Worldwide", "Kenya"])
        self.assertEqual(cfg["linkedin"]["args"][cfg["linkedin"]["args"].index("--jobage") + 1], "14")

    def test_onsite_search_skips_remote_boards(self):
        cfg = scrape_run.default_queries(settings(work_mode="onsite"))
        self.assertFalse(cfg["remote_boards"])
        self.assertEqual([r["location"] for r in cfg["linkedin"]["runs"]], ["Kenya"])


class StoreTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.saved = (scrape_run.STATE, scrape_run.TRACKER, scrape_run.POSTINGS)
        self.addCleanup(lambda: setattr_all(self.saved))
        scrape_run.STATE = root / "seen_jobs.json"
        scrape_run.TRACKER = root / "tracker.csv"
        scrape_run.POSTINGS = root / "postings"
        self.input = root / "triaged.json"

    def store(self, jobs):
        self.input.write_text(json.dumps(jobs), encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(scrape_run.cmd_store(argparse.Namespace(input=str(self.input))), 0)
        return json.loads(out.getvalue())

    def test_store_keeps_text_out_of_state_and_caches_it_guarded(self):
        text = "We need a product designer for our mobile app. " * 20
        out = self.store([hit(description=text, fit="high", status="new")])
        self.assertEqual(out["postings_cached"], 1)
        state = json.loads(scrape_run.STATE.read_text(encoding="utf-8"))["seen"]
        (key, entry), = state.items()
        self.assertNotIn("description", entry)
        self.assertEqual((entry["fit"], entry["status"], entry["posted_date"]), ("high", "new", "2026-11-20"))
        cached = (scrape_run.POSTINGS / f"{key}.txt").read_text(encoding="utf-8")
        self.assertTrue(cached.startswith("[posting_guard: "))
        self.assertIn("product designer for our mobile app", cached)

    def test_second_store_of_the_same_job_adds_nothing(self):
        self.store([hit(fit="high", status="new")])
        out = self.store([hit(url="https://jobs.test/1?utm_source=board", fit="high", status="new")])
        self.assertEqual(out["added"], [])


def setattr_all(saved):
    scrape_run.STATE, scrape_run.TRACKER, scrape_run.POSTINGS = saved


if __name__ == "__main__":
    unittest.main()
