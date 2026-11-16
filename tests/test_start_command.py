"""/start is the plain-English front door for a new user: it asks what jobs
they want, what they need from a job, their links and documents, hands off to
/setup, saves my_search.json, then runs /scrape and /rank. These tests pin
that every question is in the spec and that a blank clone triggers it."""
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
START = REPO / ".claude" / "commands" / "start.md"


class TestStartCommand(unittest.TestCase):
    def setUp(self):
        self.text = START.read_text(encoding="utf-8")
        self.low = self.text.lower()

    def test_start_command_exists_with_title(self):
        self.assertTrue(self.text.startswith("# /start - "))

    def test_start_covers_every_question(self):
        for needle in ("remote", "legally work", "lowest pay", "deal-breaker", "portfolio",
                       "documents/cv/", "my_search.json", "/scrape", "/rank", "setup.md",
                       "pay_floor_usd_year"):
            self.assertIn(needle, self.low, needle)

    def test_start_shows_progress(self):
        for n in range(1, 6):
            self.assertIn(f"step {n} of 5", self.low)

    def test_start_warns_about_pushing_profile(self):
        self.assertRegex(self.low, r"don'?t push")

    def test_user_facing_lines_are_short(self):
        # Every line the user sees is quoted with "> ". Keep each sentence short.
        for line in self.text.splitlines():
            # The Windows note is a shared instruction to Claude, not user copy.
            if not line.startswith(">") or line.startswith("> **Windows:**"):
                continue
            for sentence in re.split(r"(?<=[.?!])\s+", line.lstrip("> ").strip()):
                words = [w for w in sentence.split() if w.strip("*`")]
                self.assertLessEqual(len(words), 22, sentence)


class TestFirstRunWiring(unittest.TestCase):
    def test_claude_md_auto_trigger(self):
        head = "\n".join((REPO / "CLAUDE.md").read_text(encoding="utf-8").splitlines()[:15])
        self.assertIn("[YOUR_NAME]", head)
        self.assertIn("/start", head)

    def test_first_run_note_survives_placeholder_replacement(self):
        # /setup replaces every [PLACEHOLDER] token. The note must not carry one,
        # or it turns into "if the Name still reads Jane Doe" and fires forever.
        text = (REPO / "CLAUDE.md").read_text(encoding="utf-8")
        note = [l for l in text.splitlines()[:15] if l.startswith(">")]
        self.assertTrue(note)
        for line in note:
            self.assertNotRegex(line, r"\[[A-Z_]+\]", line)

    def test_start_deletes_first_run_note(self):
        start = START.read_text(encoding="utf-8")
        self.assertIn("delete the `> **first run:**` note", start.lower())

    def test_start_no_cv_uses_interview_path(self):
        start = START.read_text(encoding="utf-8")
        self.assertIn("If `documents/cv/` and `documents/linkedin/` are both empty", start)

    def test_start_saves_progress_and_resumes(self):
        start = START.read_text(encoding="utf-8")
        self.assertIn("start_progress.md", start)
        self.assertIn("start_progress.md", (REPO / ".gitignore").read_text(encoding="utf-8"))

    def test_search_queries_mentions_board_tools(self):
        text = (REPO / ".claude" / "skills" / "job-scraper" / "search-queries.md").read_text(encoding="utf-8")
        self.assertIn("tools/remote_boards.py", text)
        self.assertIn("tools/ats_boards.py", text)
        self.assertIn("my_search.json", text)

    def test_readme_start_here(self):
        head = "\n".join((REPO / "README.md").read_text(encoding="utf-8").splitlines()[:50])
        self.assertIn("Start here", head)
        self.assertIn("/start", head)


if __name__ == "__main__":
    unittest.main()
