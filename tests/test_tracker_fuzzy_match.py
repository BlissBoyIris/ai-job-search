"""A job already in the tracker stays out even when a board reposts it under a variant title."""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import rank_state  # noqa: E402
import scrape_state  # noqa: E402


TRACKER = """date,company,role,status
2026-11-09,Northwind,Performance Media Buyer & Creative Strategist,applied
2026-11-10,Contoso,Growth Marketing Manager (B2B SaaS / FinTech),drafted
2026-11-10,Fabrikam Logistics LLC,Paid Ads & Social Media Manager,applied
2026-11-11,Tailspin,Head of Growth / Senior Growth Manager,applied
2026-11-11,Litware,Paid Media Manager US (EST),applied
2026-11-12,Adatum,Paid Media Specialist (Meta),applied
"""


class TrackerFuzzyMatchTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "tracker.csv"
        self.path.write_text(TRACKER, encoding="utf-8")
        self.index = rank_state.tracker_pairs(self.path)

    def test_reposted_variants_of_tracked_jobs_match(self):
        for company, title in [
            ("NorthWind", "Performance Media Buyer & Creative Strategist (Remote)"),
            ("Contoso", "Growth Marketing Manager (B2B SaaS / FinTech) for DigiFi"),
            ("Fabrikam Logistics", "Hiring Remote 🚀 WE’RE HIRING: Paid Ads & Social Media Manager (Paid Ads & Multi-Channel Posting Specialist) 🚀"),
            ("Tailspin", "Head of Growth"),
            ("LITWARE Inc.", "Paid Media Manager US (EST)."),
        ]:
            with self.subTest(company=company, title=title):
                self.assertIn((company, title), self.index)

    def test_other_roles_at_the_same_company_do_not_match(self):
        for company, title in [
            ("Adatum", "Social Media Manager"),
            ("Adatum", "Performance Marketing Manager"),
            ("Tailspin", "Engineer"),
            ("Zinc", "Paid Media Specialist (Meta)"),
        ]:
            with self.subTest(company=company, title=title):
                self.assertNotIn((company, title), self.index)

    def test_legal_suffix_is_only_stripped_as_a_separate_word(self):
        self.assertEqual(rank_state.company_key("Acme Inc."), rank_state.company_key("ACME"))
        self.assertNotEqual(rank_state.company_key("Zinc"), rank_state.company_key("Z"))

    def test_tracking_query_parameters_do_not_defeat_url_dedup(self):
        a = scrape_state.canonical_url("https://jobs.test/p/1?utm_source=freehire.me")
        b = scrape_state.canonical_url("https://JOBS.test/p/1/")
        self.assertEqual(a, b)
        self.assertNotEqual(
            scrape_state.canonical_url("https://boards.test/jobs?gh_jid=1"),
            scrape_state.canonical_url("https://boards.test/jobs?gh_jid=2"),
        )


if __name__ == "__main__":
    unittest.main()
