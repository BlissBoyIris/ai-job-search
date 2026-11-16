#!/usr/bin/env python3
"""Pull remote job postings straight from company career boards.

Greenhouse, Lever and Ashby publish every company's open roles as public JSON.
Many remote startups post there first, and aggregators only mirror a fraction.
Give it company slugs (tools/ats_companies.txt, one per line, either `slug` to
probe all three systems or `ats:slug` such as `ashby:ramp`). It keeps remote
roles whose titles match your roles and that are open to where you live, using
my_search.json (written by /start).

    python3 tools/ats_boards.py --out results.json [--settings my_search.json] [--companies FILE] [--days N] [--explain]

Output matches `tools/scrape_state.py candidates`. All fields are untrusted data.
"""

import argparse
import json
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import search_settings  # noqa: E402
from remote_boards import get_json, parse_date  # noqa: E402

REMOTE = re.compile(r"remote|anywhere|worldwide|work from home|distributed", re.I)
NARROW = re.compile(
    r"\b(us|usa|u\.s\.?|united states|canada|uk|united kingdom|europe|eu|germany|france|spain|"
    r"poland|portugal|netherlands|ireland|brazil|latam|latin america|mexico|colombia|argentina|"
    r"australia|new zealand|singapore|japan|korea|philippines|south africa|nigeria|kenya|egypt|"
    r"turkey|israel|ukraine|amer|americas|north america|na|"
    r"india|pakistan|bangladesh|sri lanka|nepal|china|hong kong|taiwan|vietnam|thailand|indonesia|"
    r"malaysia|uae|united arab emirates|saudi arabia|qatar|emea|mena|middle east|apac|asia|africa|"
    r"dach|nordics|scandinavia|benelux|sweden|norway|denmark|finland|switzerland|austria|italy|"
    r"belgium|romania|czechia|chile|peru)\b",
    re.I,
)


def locations_text(texts):
    """Location strings as the posting wrote them, without the synthetic 'Remote' marker."""
    return " | ".join(t for t in texts[:-1] if t) if texts and texts[-1] == "Remote" else " | ".join(t for t in texts if t)


def remote_region_ok(texts, s):
    """texts: every location string on the posting. True when this user could apply."""
    text = " | ".join(t for t in texts if t)
    if not REMOTE.search(text):
        return False, "not remote"
    loc = locations_text(texts)
    if not loc.strip():
        return True, "remote, no region"
    ok, reason = s.region_ok(loc)
    if ok or reason.startswith("skipped"):
        return ok, reason.split(":")[0]
    # A named city beside a remote flag means "remote within that hub's region", not worldwide.
    if not re.search(r"remote|anywhere|distributed|work from home", loc, re.I):
        return False, "city-based, remote flag only"
    if NARROW.search(loc):
        return False, "country-restricted"
    return True, "remote, no region"


def greenhouse(slug):
    d = get_json(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
    for j in d.get("jobs", []):
        loc = (j.get("location") or {}).get("name", "")
        yield {"title": j["title"], "url": j["absolute_url"], "loc": [loc],
               "date": parse_date(j.get("first_published") or j.get("updated_at"))}


def lever(slug):
    for j in get_json(f"https://api.lever.co/v0/postings/{slug}?mode=json"):
        cat = j.get("categories") or {}
        locs = [cat.get("location", ""), *(cat.get("allLocations") or [])]
        if str(j.get("workplaceType", "")).lower() == "remote":
            locs.append("Remote")
        yield {"title": j["text"], "url": j["hostedUrl"], "loc": locs,
               "date": parse_date(int(j["createdAt"]) // 1000) if j.get("createdAt") else None}


def ashby(slug):
    d = get_json(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
    for j in d.get("jobs", []):
        locs = [j.get("location", ""), *(s.get("location", "") for s in j.get("secondaryLocations") or [])]
        if j.get("isRemote") or str(j.get("workplaceType", "")).lower() == "remote":
            locs.append("Remote")
        yield {"title": j["title"], "url": j.get("jobUrl") or j.get("applyUrl", ""), "loc": locs,
               "date": parse_date(j.get("publishedAt"))}


SYSTEMS = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby}


def probe(entry):
    """Return (ats, slug, company, [postings]) for the first system that has this board."""
    ats, _, slug = entry.partition(":") if ":" in entry else ("", "", entry)
    for name in ([ats] if ats else SYSTEMS):
        try:
            jobs = list(SYSTEMS[name](slug))
        except Exception:  # noqa: BLE001 - a missing board is the normal case when probing
            continue
        return name, slug, jobs
    return None, slug, []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--companies", default=str(Path(__file__).with_name("ats_companies.txt")))
    ap.add_argument("--settings", default=str(search_settings.DEFAULT_PATH))
    ap.add_argument("--days", type=int, default=None, help="default: max_age_days from settings")
    ap.add_argument("--explain", action="store_true")
    args = ap.parse_args()

    try:
        s = search_settings.load(args.settings)
    except search_settings.SettingsMissing as exc:
        print(exc, file=sys.stderr)
        return 1
    if s.work_mode == "onsite":
        Path(args.out).write_text("[]", encoding="utf-8")
        print("Skipped: you asked for on-site jobs only, and this tool only keeps remote jobs.")
        return 0
    if not s.roles:
        print("No job titles in your settings. Run /start to add some.", file=sys.stderr)
        return 1
    title_yes, title_no = s.title_yes(), s.title_no()

    entries = [ln.split("#")[0].strip() for ln in Path(args.companies).read_text(encoding="utf-8").splitlines()]
    entries = [e for e in dict.fromkeys(entries) if e]
    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days or s.max_age_days)

    with ThreadPoolExecutor(max_workers=12) as pool:
        boards = list(pool.map(probe, entries))

    why, kept, found, missing = Counter(), [], [], []
    for ats, slug, jobs in boards:
        if not ats:
            missing.append(slug)
            continue
        found.append(f"{ats}:{slug}")
        for j in jobs:
            t = j["title"]
            if not title_yes.search(t) or title_no.search(t):
                why["title"] += 1
                continue
            if j["date"] and j["date"] < cutoff:
                why["older than window"] += 1
                continue
            ok, reason = remote_region_ok(j["loc"], s)
            if not ok:
                why[reason] += 1
                continue
            kept.append({
                "title": t, "company": slug, "url": j["url"],
                "location": next((x for x in j["loc"] if x), "Remote"),
                "date": j["date"].date().isoformat() if j["date"] else None,
                "portal": ats, "source": "cli", "region_note": reason,
            })
    Path(args.out).write_text(json.dumps(kept, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"companies_listed": len(entries), "boards_found": len(found), "kept": len(kept),
                      "no_board": missing if args.explain else len(missing),
                      **({"dropped": why, "found": found} if args.explain else {})}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
