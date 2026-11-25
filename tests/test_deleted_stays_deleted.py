"""A job deleted on the dashboard never comes back: not as a repost, not through a later score."""

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
import rank_state  # noqa: E402
import scrape_state  # noqa: E402

DELETED = {"title": "Growth Marketing Manager (B2B SaaS / FinTech)", "company": "Contoso",
           "url": "https://jobs.test/a", "status": "skipped", "skipped_by": "dashboard"}


class DeletedStaysDeleted(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.state = self.root / "seen_jobs.json"
        self.tracker = self.root / "tracker.csv"

    def write(self, seen):
        self.state.write_text(json.dumps({"seen": seen}), encoding="utf-8")

    def test_scrape_drops_a_repost_of_a_deleted_job(self):
        self.write({"sat": DELETED})
        repost = {"title": "Growth Marketing Manager (B2B SaaS / FinTech) for DigiFi", "company": "Contoso Inc.",
                  "url": "https://other.test/b"}
        other = {"title": "Creative Strategist", "company": "Contoso", "url": "https://other.test/c"}
        selected, counts = scrape_state.select([repost, other], json.loads(self.state.read_text())["seen"], set())
        self.assertEqual(selected, [other])
        self.assertEqual(counts["already_deleted"], 1)

    def test_rank_skips_reposts_and_never_rescores_a_deleted_job(self):
        repost = {"title": "Growth Marketing Manager (B2B SaaS / FinTech) for DigiFi", "company": "Contoso",
                  "url": "https://jobs.test/b", "status": "new"}
        self.write({"sat": dict(DELETED), "rep": repost})
        out = io.StringIO()
        args = argparse.Namespace(state=self.state, tracker=self.tracker, all=False, focus=None, limit=10)
        with contextlib.redirect_stdout(out):
            rank_state.cmd_candidates(args)
        self.assertEqual(json.loads(out.getvalue())["selected"], [])

        results = self.root / "results.json"
        results.write_text(json.dumps([{"key": "sat", "status": "scored",
            "scores": {"technical": 90, "experience": 90, "behavioral": 90, "career": 90},
            "location_verdict": "PASS", "language_gate": "PASS", "strengths": [], "gaps": []}]), encoding="utf-8")
        out = io.StringIO()
        args = argparse.Namespace(state=self.state, results=results, today=rank_state.date.today(),
                                  now=rank_state.datetime.now(rank_state.timezone.utc), dry_run=False)
        with contextlib.redirect_stdout(out):
            rank_state.cmd_apply(args)
        self.assertEqual(json.loads(out.getvalue())["kept_deleted"], ["sat"])
        self.assertEqual(json.loads(self.state.read_text())["seen"]["sat"]["status"], "skipped")


if __name__ == "__main__":
    unittest.main()
