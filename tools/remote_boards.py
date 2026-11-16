#!/usr/bin/env python3
"""Pull remote job postings from boards that publish open JSON/RSS feeds.

Sources: Remotive, RemoteOK, Himalayas, Jobicy, We Work Remotely. No login, no
scraping of rendered pages. Filters come from my_search.json (written by
/start, read via search_settings.py): job titles, where the user can be hired
from, the lowest stated pay they take, and how old a posting may be.

    python3 tools/remote_boards.py --out results.json [--settings my_search.json] [--days N] [--explain]

These boards only list remote work, so an on-site-only search writes an empty
list and says so. The output is a JSON array of {title, company, url, location,
date, salary, portal, source} - the shape `tools/scrape_state.py candidates`
expects. All fields are untrusted third-party data.
"""

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import search_settings  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (job-search personal use)"}

def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def get_json(url):
    return json.loads(get(url).decode("utf-8", "replace"))


def strip_tags(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()


def parse_date(value):
    if value in (None, "", "None"):
        return None
    try:
        if str(value).isdigit():
            return datetime.fromtimestamp(int(value), tz=timezone.utc)
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def annual_usd(lo, hi, currency, period):
    """Annual USD figure for the pay, or None when unstated or not USD."""
    try:
        val = float(lo or hi or 0)
    except (TypeError, ValueError):
        return None
    if val <= 0 or (currency and str(currency).upper() not in ("USD", "NONE", "")):
        return None
    period = (period or "annual").lower()
    if period.startswith("month"):
        val *= 12
    elif period.startswith("hour"):
        val *= 2080
    elif period.startswith("week"):
        val *= 52
    return val


def desc_restricts(desc, s):
    """True when the description says candidates must live in a skipped region."""
    if not s.skip_regions or not desc:
        return False
    places = "|".join(re.escape(r) for r in s.skip_regions)
    return bool(re.search(
        rf"(must|should)\s+(be\s+)?(based|located|reside|live)\s+in\s+({places})|"
        rf"({places})[- ]based\s+(candidates|only)|candidates\s+(from|in)\s+({places})\s+only",
        desc, re.I))


def keep(job, cutoff, why, s):
    t = job["title"]
    if not s.title_yes().search(t):
        why["title not one of your roles"] += 1
        return False
    if s.title_no().search(t):
        why["title has a word you skip"] += 1
        return False
    if job.get("posted") and job["posted"] < cutoff:
        why["older than window"] += 1
        return False
    ok, reason = job["_region"]
    if not ok:
        why[reason.split(":")[0]] += 1
        return False
    if s.pay_floor_usd_year and job.get("_annual") is not None and job["_annual"] < s.pay_floor_usd_year:
        why["stated pay below your floor"] += 1
        return False
    if desc_restricts(job.get("_desc", ""), s):
        why["description restricts to a skipped region"] += 1
        return False
    return True


def remotive(s):
    out = []
    for q in s.roles:
        try:
            data = get_json("https://remotive.com/api/remote-jobs?search=" + urllib.parse.quote(q))
        except Exception as exc:  # noqa: BLE001 - one dead feed must not stop the run
            print(f"remotive: {exc}", file=sys.stderr)
            continue
        for j in data.get("jobs", []):
            loc = j.get("candidate_required_location", "")
            out.append({
                "title": j["title"], "company": j["company_name"], "url": j["url"],
                "location": loc, "posted": parse_date(j.get("publication_date")),
                "salary": j.get("salary") or None, "portal": "remotive",
                "_region": s.region_ok(loc), "_desc": strip_tags(j.get("description", ""))[:3000],
                "_annual": None,
            })
    return out


def remoteok(s):
    out = []
    try:
        data = get_json("https://remoteok.com/api")
    except Exception as exc:  # noqa: BLE001
        print(f"remoteok: {exc}", file=sys.stderr)
        return out
    for j in data[1:]:
        if not isinstance(j, dict) or not j.get("position"):
            continue
        loc = j.get("location", "")
        lo, hi = j.get("salary_min"), j.get("salary_max")
        out.append({
            "title": j["position"], "company": j.get("company", ""), "url": j.get("url", ""),
            "location": loc, "posted": parse_date(j.get("date")),
            "salary": f"{lo}-{hi} USD" if lo and str(lo) != "0" else None, "portal": "remoteok",
            "_region": s.region_ok(loc), "_desc": strip_tags(j.get("description", ""))[:3000],
            "_annual": annual_usd(lo, hi, "USD", "annual"),
        })
    return out


def himalayas(s):
    out = []
    for q in s.roles:
        try:
            data = get_json("https://himalayas.app/jobs/api/search?sort=recent&q=" + urllib.parse.quote(q))
        except Exception as exc:  # noqa: BLE001
            print(f"himalayas '{q}': {exc}", file=sys.stderr)
            continue
        for j in data.get("jobs", []):
            restr = j.get("locationRestrictions") or []
            lo, hi = j.get("minSalary"), j.get("maxSalary")
            out.append({
                "title": j["title"], "company": j["companyName"],
                "url": j.get("applicationLink") or j.get("guid", ""),
                "location": ", ".join(restr) if restr else "Worldwide",
                "posted": parse_date(j.get("pubDate")),
                "salary": f"{lo}-{hi} {j.get('currency')}/{j.get('salaryPeriod')}" if lo else None,
                "portal": "himalayas", "_region": s.region_ok("", restr),
                "_desc": strip_tags(j.get("description", ""))[:3000],
                "_annual": annual_usd(lo, hi, j.get("currency"), j.get("salaryPeriod")),
            })
    return out


def jobicy(s):
    out = []
    for url in ["https://jobicy.com/api/v2/remote-jobs?count=100&tag=" + urllib.parse.quote(q) for q in s.roles]:
        try:
            data = get_json(url)
        except Exception as exc:  # noqa: BLE001
            print(f"jobicy: {exc}", file=sys.stderr)
            continue
        for j in data.get("jobs", []):
            loc = j.get("jobGeo", "")
            lo, hi = j.get("salaryMin"), j.get("salaryMax")
            out.append({
                "title": j["jobTitle"], "company": j["companyName"], "url": j["url"],
                "location": loc, "posted": parse_date(j.get("pubDate")),
                "salary": f"{lo}-{hi} {j.get('salaryCurrency')}/{j.get('salaryPeriod')}" if lo else None,
                "portal": "jobicy", "_region": s.region_ok(loc),
                "_desc": strip_tags(j.get("jobDescription", ""))[:3000],
                "_annual": annual_usd(lo, hi, j.get("salaryCurrency"), j.get("salaryPeriod")),
            })
    return out


def weworkremotely(s):
    out = []
    for feed in ("remote-jobs",):
        try:
            root = ET.fromstring(get(f"https://weworkremotely.com/{feed}.rss"))
        except Exception as exc:  # noqa: BLE001
            print(f"wwr {feed}: {exc}", file=sys.stderr)
            continue
        for item in root.iter("item"):
            raw = (item.findtext("title") or "").strip()
            company, _, title = raw.partition(": ")
            region = (item.findtext("region") or item.findtext("{*}region") or "").strip()
            try:
                posted = parsedate(item.findtext("pubDate"))
            except Exception:  # noqa: BLE001
                posted = None
            out.append({
                "title": title or raw, "company": company, "url": (item.findtext("link") or "").strip(),
                "location": region, "posted": posted, "salary": None, "portal": "weworkremotely",
                "_region": s.region_ok(region), "_desc": strip_tags(item.findtext("description") or "")[:3000],
                "_annual": None,
            })
    return out


def parsedate(value):
    from email.utils import parsedate_to_datetime
    return parsedate_to_datetime(value) if value else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--settings", default=str(search_settings.DEFAULT_PATH))
    ap.add_argument("--days", type=int, default=None, help="default: max_age_days from settings")
    ap.add_argument("--explain", action="store_true", help="print why postings were dropped")
    args = ap.parse_args()

    try:
        s = search_settings.load(args.settings)
    except search_settings.SettingsMissing as exc:
        print(exc, file=sys.stderr)
        return 1
    if s.work_mode == "onsite":
        Path(args.out).write_text("[]", encoding="utf-8")
        print("Skipped: you asked for on-site jobs only, and these boards list remote jobs.")
        return 0
    if not s.roles:
        print("No job titles in your settings. Run /start to add some.", file=sys.stderr)
        return 1

    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days or s.max_age_days)
    pool = []
    for fn in (remotive, remoteok, himalayas, jobicy, weworkremotely):
        pool.extend(fn(s))

    why = Counter()
    kept, seen = [], set()
    for job in pool:
        if not job["url"].startswith("http") or not job["company"] or job["url"] in seen:
            continue
        seen.add(job["url"])
        if keep(job, cutoff, why, s):
            kept.append({
                "title": job["title"], "company": job["company"], "url": job["url"],
                "location": job["location"] or "Remote (no region stated)",
                "date": job["posted"].date().isoformat() if job["posted"] else None,
                "salary": job["salary"], "portal": job["portal"], "source": "cli",
            })
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(kept, fh, ensure_ascii=False, indent=1)
    per = Counter(j["portal"] for j in kept)
    print(json.dumps({"fetched": len(seen), "kept": len(kept), "by_portal": per,
                      **({"dropped": why} if args.explain else {})}, default=dict, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
