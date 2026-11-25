#!/usr/bin/env python3
"""Scripted /scrape: run every portal query, filter and dedupe in code, no model.

    python3 tools/scrape_run.py search --out pool.json [--broad] [--no-linkedin]
    python3 tools/scrape_run.py store --in triaged.json

`search` runs freehire and LinkedIn searches for the job titles in my_search.json
(written by /start; job_scraper/queries.json overrides them, see
job_scraper/queries.example.json), plus tools/remote_boards.py and, when
job_scraper/watchlist.json exists, tools/watchlist.py (careers pages of companies
you follow). It applies your my_search.json filters (titles, work mode, where you
can be hired from), drops anything already seen, applied to or deleted
(scrape_state.select), and writes the surviving hits WITH their posting text. The caller sorts them by fit (one cheap
model call over titles) and sets `fit` and `status` on each.

`store` writes those entries to seen_jobs.json through scrape_state's store
path (same keys, same checks) and saves each posting's guarded text to
job_scraper/postings/<key>.txt, so /rank and the CV writer never fetch it again.

All portal output is untrusted third-party data.
"""

import argparse
import contextlib
import io
import json
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import posting_guard  # noqa: E402
import remote_boards  # noqa: E402
import scrape_state  # noqa: E402
import search_settings  # noqa: E402
from job_key import make_key  # noqa: E402
from rank_state import STATE, TRACKER, _force_utf8_output, load_state, tracker_pairs  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
QUERIES = ROOT / "job_scraper" / "queries.json"
POSTINGS = ROOT / "job_scraper" / "postings"
FREEHIRE = [".agents/skills/freehire-search/cli/src/cli.ts", "search"]
LINKEDIN = [".agents/skills/linkedin-search/cli/src/cli.ts", "search"]

LINKEDIN_AGES = (1, 7, 14, 30)  # the only windows LinkedIn's --jobage accepts
ON_SITE_TITLE = re.compile(r"\b(hybrid|on-?site|in[- ]office)\b", re.I)


def title_ok(title: str, s) -> bool:
    return bool(s.title_yes().search(title)) and not s.title_no().search(title)


def default_queries(s) -> dict:
    """Searches built from my_search.json when job_scraper/queries.json is absent."""
    mode = [] if s.work_mode == "any" else ["--remote", s.work_mode]
    groups = [s.roles[i:i + 5] for i in range(0, len(s.roles), 5)]
    li_age = next((d for d in LINKEDIN_AGES if d >= s.max_age_days), 30)
    places = (["Worldwide"] if s.work_mode == "remote" else []) + ([s.home_country] if s.home_country else [])
    return {
        "freehire": {
            "args": [*mode, "--jobage", str(s.max_age_days), "--limit", "50"],
            "pages": [1, 2],
            "queries": [" OR ".join(f"title:{r}" for r in g) for g in groups],
        },
        "linkedin": {
            "args": [*mode, "--jobage", str(li_age), "--limit", "20"],
            "runs": [{"location": place, "queries": s.roles[:8]} for place in places],
        },
        "remote_boards": s.work_mode != "onsite",
    }


def run_cli(args: list[str]) -> list[dict]:
    # stdout goes to a file, not a pipe: bun exits before flushing a pipe past 64 KB,
    # which cuts freehire's full-description output mid-JSON.
    with tempfile.TemporaryFile() as out:
        try:
            p = subprocess.run(["bun", "run", *args, "--format", "json"], cwd=ROOT, stdout=out,
                               stderr=subprocess.PIPE, timeout=120)
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(f"portal call failed: {exc}", file=sys.stderr)
            return []
        out.seek(0)
        raw = out.read().decode("utf-8", "replace")
    if p.returncode != 0:
        print(f"portal call failed ({' '.join(args[2:6])}): {p.stderr.decode('utf-8', 'replace').strip()[:200]}", file=sys.stderr)
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        print(f"portal output unreadable ({' '.join(args[2:6])})", file=sys.stderr)
        return []
    return data.get("results", []) if isinstance(data, dict) else data


def as_list(value) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.startswith("["):
        try:
            return json.loads(value.replace("'", '"'))
        except json.JSONDecodeError:
            return []
    return []


def freehire_hits(cfg: dict) -> list[dict]:
    calls = [[*FREEHIRE, "-q", q, *cfg["args"], "--page", str(page)] for q in cfg["queries"] for page in cfg["pages"]]
    calls += [[*FREEHIRE, "-q", q, *cfg["args"], "--page", "3"] for q in cfg.get("page3_queries", [])]
    out = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for results in pool.map(run_cli, calls):
            for r in results:
                regions, countries = as_list(r.get("regions")), as_list(r.get("countries"))
                out.append({
                    "title": r.get("title"), "company": r.get("company"), "url": r.get("url"),
                    "location": r.get("location"), "date": r.get("date"), "description": r.get("description") or "",
                    "portal": "freehire-search", "source": "cli", "_regions": regions, "_countries": countries,
                })
    return out


def linkedin_hits(runs: list[dict], args: list[str]) -> list[dict]:
    out = []
    for run in runs:  # sequential and small on purpose: LinkedIn personal-use ToS
        for q in run["queries"]:
            for r in run_cli([*LINKEDIN, "-q", q, "-l", run["location"], *args]):
                out.append({
                    "title": r.get("title"), "company": r.get("company"), "url": r.get("url"),
                    "location": r.get("location"), "date": r.get("date"), "description": "",
                    "portal": "linkedin-search", "source": "cli",
                })
    return out


def board_hits(settings_path) -> list[dict]:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "boards.json"
        p = subprocess.run([sys.executable, "tools/remote_boards.py", "--out", str(path), "--with-description",
                            "--settings", str(settings_path)],
                           cwd=ROOT, capture_output=True, text=True, timeout=600)
        if p.returncode != 0 or not path.exists():
            print(f"remote boards failed: {p.stderr.strip()[:200]}", file=sys.stderr)
            return []
        return [{**j, "_region_checked": True} for j in json.loads(path.read_text(encoding="utf-8"))]


def watchlist_hits(settings_path) -> list[dict]:
    """Careers pages of companies you follow (job_scraper/watchlist.json), via tools/watchlist.py."""
    if not (ROOT / "job_scraper" / "watchlist.json").exists():
        return []
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "watch.json"
        p = subprocess.run([sys.executable, "tools/watchlist.py", "--out", str(path), "--with-description",
                            "--settings", str(settings_path)],
                           cwd=ROOT, capture_output=True, text=True, timeout=600)
        if p.returncode != 0 or not path.exists():
            print(f"watchlist failed: {p.stderr.strip()[:200]}", file=sys.stderr)
            return []
        return [{**j, "_region_checked": True} for j in json.loads(path.read_text(encoding="utf-8"))]


def hard_filter(job: dict, why: dict, s) -> bool:
    def drop(reason):
        why[reason] = why.get(reason, 0) + 1
        return False
    title, loc = str(job.get("title") or ""), str(job.get("location") or "")
    if not title_ok(title, s):
        return drop("title")
    # The board tools already checked the region; freehire tags worldwide jobs "global".
    if not job.get("_region_checked") and "global" not in (job.get("_regions") or []):
        ok, reason = s.region_ok(loc)
        if not ok:
            return drop(reason.split(":")[0])
    if remote_boards.desc_restricts(job.get("description", ""), s):
        return drop("description restricts to a skipped region")
    if s.work_mode == "remote" and ON_SITE_TITLE.search(title):
        return drop("hybrid/on-site")
    return True


def cmd_search(args) -> int:
    try:
        s = search_settings.load(args.settings)
    except search_settings.SettingsMissing as exc:
        print(exc, file=sys.stderr)
        return 1
    if not s.roles:
        print("No job titles in your settings. Run /start to add some.", file=sys.stderr)
        return 1
    cfg = json.loads(QUERIES.read_text(encoding="utf-8")) if QUERIES.exists() else default_queries(s)
    pool = freehire_hits(cfg["freehire"]) if cfg.get("freehire") else []
    if not args.no_linkedin and cfg.get("linkedin"):
        li = cfg["linkedin"]
        pool += linkedin_hits(li["runs"] + (li.get("broad_runs", []) if args.broad else []), li["args"])
    if cfg.get("remote_boards", True) and s.work_mode != "onsite":
        pool += board_hits(args.settings)
    if cfg.get("watchlist", True):
        pool += watchlist_hits(args.settings)
    fetched = len(pool)

    why: dict = {}
    kept = [j for j in pool if isinstance(j, dict) and hard_filter(j, why, s)]
    seen = load_state(STATE)[1] if STATE.exists() else {}
    selected, counts = scrape_state.select(kept, seen, tracker_pairs(TRACKER))
    for job in selected:
        job.pop("_regions", None)
        job.pop("_countries", None)
        job.pop("_region_checked", None)
    Path(args.out).write_text(json.dumps(selected, ensure_ascii=False), encoding="utf-8")
    by_portal: dict = {}
    for j in selected:
        by_portal[j["portal"]] = by_portal.get(j["portal"], 0) + 1
    print(json.dumps({
        "fetched": fetched, "filtered_out": why, "already_seen": counts["already_seen"],
        "already_applied": counts["already_applied"], "already_deleted": counts["already_deleted"], "repeated": counts["repeated_in_batch"],
        "invalid": len(counts["invalid"]), "new": len(selected), "by_portal": by_portal,
    }))
    return 0


def cmd_store(args) -> int:
    jobs = json.loads(Path(args.input).read_text(encoding="utf-8"))
    today = date.today().isoformat()
    entries, texts = [], {}
    for job in jobs:
        text = job.pop("description", "") or ""
        entry = {
            "title": job["title"], "company": job["company"], "url": job["url"], "location": job.get("location"),
            "first_seen": today, "posted_date": job.get("date"), "deadline": None,
            "fit": job["fit"], "status": job["status"], "portal": job["portal"], "source": job.get("source", "cli"),
        }
        entries.append(entry)
        if len(text.strip()) >= 300:
            texts[make_key(entry["company"], entry["title"], entry["url"])] = text

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "store.json"
        path.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
        ns = argparse.Namespace(command="store", results=path, state=STATE, tracker=TRACKER, portal=None, domain=None)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = scrape_state.run(ns)
        if rc != 0:
            return rc
        result = json.loads(buf.getvalue())

    POSTINGS.mkdir(parents=True, exist_ok=True)
    cached = 0
    for key in result.get("added", []):
        if key in texts:
            cleaned, findings = posting_guard.guard(texts[key], "auto")
            verdict = findings.get("verdict", "")
            (POSTINGS / f"{key}.txt").write_text(f"[posting_guard: {verdict}]\n\n{cleaned}", encoding="utf-8")
            cached += 1
    print(json.dumps({**result, "postings_cached": cached}))
    return 0


def main() -> int:
    _force_utf8_output()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="command", required=True)
    s = sub.add_parser("search")
    s.add_argument("--out", required=True)
    s.add_argument("--broad", action="store_true")
    s.add_argument("--no-linkedin", action="store_true")
    s.add_argument("--settings", default=str(search_settings.DEFAULT_PATH))
    st = sub.add_parser("store")
    st.add_argument("--in", dest="input", required=True)
    args = ap.parse_args()
    try:
        return cmd_search(args) if args.command == "search" else cmd_store(args)
    except (ValueError, KeyError) as exc:
        print(f"scrape_run: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
