#!/usr/bin/env python3
"""Read the job-search answers that /start saves in my_search.json.

The board tools (remote_boards.py, ats_boards.py) use this to decide which
postings to keep: job titles, where the user can be hired from, the lowest pay
they will take, and how old a posting may be. Missing keys fall back to safe
defaults, so a hand-edited file still works.

my_search.json lives in the repo root and is gitignored (it holds personal data).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "my_search.json"
WIDE = ["worldwide", "anywhere", "global"]
ALWAYS_SKIP_TITLES = ["intern", "internship"]
WORK_MODES = ("remote", "hybrid", "onsite", "any")


class SettingsMissing(Exception):
    """my_search.json is missing or unreadable."""


def _words(items):
    return [str(i).strip().lower() for i in items or [] if str(i).strip()]


# Short and long names for the same country, so "Remote - US" counts for a user
# who wrote "United States". Lowercase; matched as whole words.
ALIASES = [
    ["united states", "united states of america", "usa", "us", "u.s.", "u.s.a.", "america"],
    ["united kingdom", "uk", "u.k.", "great britain", "britain", "gb", "england"],
    ["united arab emirates", "uae", "u.a.e."],
    ["netherlands", "the netherlands", "holland"],
    ["south korea", "korea", "republic of korea"],
    ["czechia", "czech republic"],
    ["turkey", "turkiye", "türkiye"],
]
# Place names that contain a shorter place name. In free text they are blanked
# out first, so "Africa" never matches "South Africa" unless the user named it.
COMPOUND_PLACES = [
    "south africa", "south sudan", "north korea", "south korea", "north macedonia",
    "papua new guinea", "new guinea", "east timor", "west bank", "new mexico",
]
UNQUALIFIED_REMOTE = re.compile(r"\s*(100\s*%\s*|fully\s+|full[- ]time\s+)?remote(\s*\(?(anywhere|worldwide)\)?)?\s*", re.I)


def _expand(names):
    """Each name plus its other spellings."""
    out = set()
    for n in names:
        n = n.strip().lower()
        if not n:
            continue
        out.add(n)
        for group in ALIASES:
            if n in group:
                out.update(group)
    return sorted(out)


def _pattern(words):
    if not words:
        return re.compile(r"(?!x)x")  # matches nothing
    alts = [r"(?<![a-z0-9])" + re.escape(w).replace(r"\ ", r"[\s-]+") + r"(?![a-z0-9])" for w in words]
    return re.compile("|".join(alts), re.I)


@dataclass
class Settings:
    roles: list = field(default_factory=list)
    title_skip: list = field(default_factory=list)
    work_mode: str = "remote"
    home_city: str = ""
    home_country: str = ""
    open_to_regions: list = field(default_factory=lambda: list(WIDE))
    skip_regions: list = field(default_factory=list)
    pay_floor_usd_year: float | None = None
    max_age_days: int = 30

    def title_yes(self):
        return _pattern(self.roles)

    def title_no(self):
        return _pattern(self.title_skip + ALWAYS_SKIP_TITLES)

    def _home_names(self):
        return _expand([w for w in (self.home_country, self.home_city) if w])

    def _own_terms(self):
        return set(self._home_names()) | set(_expand(self.open_to_regions)) | set(_expand(self.skip_regions))

    def _clean(self, text):
        """Blank out compound place names the user did not name themselves."""
        own = self._own_terms()
        for place in COMPOUND_PLACES:
            if place not in own:
                text = _pattern([place]).sub(" ", text)
        return text

    def region_ok(self, text, restrictions=None):
        """Can this user be hired for a posting with this location text or
        list of allowed countries? Returns (ok, short reason)."""
        if restrictions is not None and not restrictions:
            return True, "no restriction"
        joined = ", ".join(restrictions) if restrictions else (text or "")
        if not joined.strip():
            return True, "no region stated"
        home = _pattern(self._home_names())
        wide = _pattern(_expand(self.open_to_regions))
        if not restrictions:
            joined = self._clean(joined)
        if self.skip_regions and _pattern(_expand(self.skip_regions)).search(joined):
            if not (home.search(joined) or _pattern(WIDE).search(joined)):
                return False, f"skipped region: {joined[:60]}"
        if restrictions:
            # A list of allowed countries: match whole items, so "Africa" never
            # matches "South Africa" and "Sudan" never matches "South Sudan".
            items = {str(r).strip().lower() for r in restrictions}
            if items & set(_expand([self.home_country])):
                return True, "home country allowed"
            if items & set(_expand(self.open_to_regions)):
                return True, "open region"
            return False, f"not open to you: {joined[:60]}"
        if home.search(joined):
            return True, "home country allowed"
        if wide.search(joined) or UNQUALIFIED_REMOTE.fullmatch(joined):
            return True, "open region"
        return False, f"not open to you: {joined[:60]}"


def load(path=None):
    path = Path(path) if path else DEFAULT_PATH
    if not path.exists():
        raise SettingsMissing(
            f"No search settings found at {path.name}. Run /start first - it asks what jobs you want and saves them."
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("top level is not an object")
    except (ValueError, OSError) as exc:
        raise SettingsMissing(
            f"{path.name} could not be read ({exc}). Run /start again to rewrite it."
        ) from exc
    home = raw.get("home") or {}
    mode = str(raw.get("work_mode") or "remote").lower().replace("-", "").replace(" ", "")
    floor = raw.get("pay_floor_usd_year")
    try:
        floor = float(floor) if floor not in (None, "", 0) else None
    except (TypeError, ValueError):
        floor = None
    try:
        days = int(raw.get("max_age_days") or 30)
    except (TypeError, ValueError):
        days = 30
    return Settings(
        roles=_words(raw.get("roles")),
        title_skip=_words(raw.get("title_skip")),
        work_mode=mode if mode in WORK_MODES else "remote",
        home_city=str(home.get("city") or "").strip(),
        home_country=str(home.get("country") or "").strip(),
        open_to_regions=sorted(set(WIDE + _words(raw.get("open_to_regions")))),
        skip_regions=_words(raw.get("skip_regions")),
        pay_floor_usd_year=floor,
        max_age_days=max(1, days),
    )
