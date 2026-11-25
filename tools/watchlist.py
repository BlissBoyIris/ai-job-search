#!/usr/bin/env python3
"""Poll the careers pages of companies you follow (repeat posters of roles that score well for you).

    python3 tools/watchlist.py --out hits.json [--settings my_search.json] [--days N] [--explain]
    python3 tools/watchlist.py --suggest

The list lives in job_scraper/watchlist.json: {"companies": [{"name", "ats", "slug"}]}.
Supported `ats` values and what `slug` means:

    workable    apply.workable.com account slug        (widget API, all locations listed)
    teamtailor  careers site host, e.g. careers.x.com  (<host>/jobs.rss)
    manatal     careers-page.com slug                  (Manatal open career-page API)
    bamboohr    <slug>.bamboohr.com                    (/careers/list JSON)
    zoho        <slug>.zohorecruit.com (or .eu host)   (job objects embedded in the careers page)
    greenhouse / lever / ashby                         (reuses tools/ats_boards.py fetchers)

Output is the same job dict shape remote_boards.py writes (portal="watchlist"), and the
same title / region / pay / age filters from my_search.json apply. `--suggest` lists repeat posters (2+ ranked,
one 70+ or two 60+) in seen_jobs.json that are not on the list yet; it only prints.
All fetched content is untrusted third-party data.
"""

import argparse
import html as htmllib
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ats_boards  # noqa: E402
import remote_boards as rb  # noqa: E402
import search_settings  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
WATCHLIST = ROOT / "job_scraper" / "watchlist.json"
SEEN = ROOT / "job_scraper" / "seen_jobs.json"
S = None  # search_settings.Settings, loaded in main()


def region_ok(text, restrictions=None):
    return S.region_ok(text, restrictions)


def job(company, title, url, location, posted, region, desc="", salary=None, annual=None):
    return {"title": title or "", "company": company, "url": url or "", "location": location or "Remote",
            "posted": posted, "salary": salary, "portal": "watchlist", "_region": region,
            "_desc": rb.strip_tags(desc)[:12000], "_annual": annual}


def workable(c):
    d = rb.get_json(f"https://apply.workable.com/api/v1/widget/accounts/{c['slug']}")
    out = []
    for j in d.get("jobs", []):
        if str(j.get("telecommuting")).lower() != "true":
            continue
        countries = [loc.get("country") for loc in (j.get("locations") or []) if loc.get("country")]
        if not countries and j.get("country"):
            countries = [j["country"]]
        # Workable lists every country the job is open to; the user's has to be one of them.
        region = region_ok("", countries) if countries else (True, "no region stated")
        place = f"Remote - {S.home_country or 'your country'} listed" if region[0] and countries else ("Remote - " + ", ".join(countries[:3]) if countries else "Remote")
        out.append(job(c["name"], j.get("title"), j.get("shortlink") or j.get("url"), place,
                       rb.parse_date(j.get("published_on") or j.get("created_at")), region))
    return out


def teamtailor(c):
    root = ET.fromstring(rb.get(f"https://{c['slug']}/jobs.rss"))
    out = []
    for item in root.iter("item"):
        status = (item.findtext("remoteStatus") or "").strip().lower()
        if status not in ("fully", "remote"):
            continue
        locs = [x.text.strip() for x in item.iter() if x.tag.endswith("}country") or x.tag.endswith("}city") if x.text]
        text = ", ".join(dict.fromkeys(locs))
        try:
            posted = rb.parsedate(item.findtext("pubDate"))
        except Exception:  # noqa: BLE001
            posted = None
        out.append(job(c["name"], (item.findtext("title") or "").strip(), (item.findtext("link") or "").strip(),
                       text or "Remote", posted, region_ok(text) if text else (True, "no region stated"),
                       htmllib.unescape(item.findtext("description") or "")))
    return out


def manatal(c):
    d = rb.get_json(f"https://core.api.manatal.com/open/v3/career-page/{c['slug']}/jobs/")
    out = []
    for j in d.get("results", []):
        title = j.get("position_name") or ""
        place = ", ".join(x for x in (j.get("city"), j.get("country")) if x) or j.get("location_display") or ""
        if not (j.get("is_remote") or re.search(r"remote", f"{title} {place}", re.I)):
            continue
        out.append(job(c["name"], title, f"https://www.careers-page.com/{c['slug']}/job/{j.get('hash')}",
                       place or "Remote", rb.parse_date(j.get("created_at") or j.get("updated_at")),
                       region_ok(place) if place else (True, "no region stated"), j.get("description") or ""))
    return out


def bamboohr(c):
    req = rb.urllib.request.Request(f"https://{c['slug']}.bamboohr.com/careers/list",
                                    headers={**rb.UA, "Accept": "application/json"})
    with rb.urllib.request.urlopen(req, timeout=30) as resp:
        d = json.loads(resp.read().decode("utf-8", "replace"))
    out = []
    for j in d.get("result", []):
        if str(j.get("locationType")) != "1" and not j.get("isRemote"):
            continue
        loc = j.get("atsLocation") or {}
        # BambooHR's atsLocation is the company's office, not a hiring limit; region is checked at /rank.
        out.append(job(c["name"], j.get("jobOpeningName"), f"https://{c['slug']}.bamboohr.com/careers/{j.get('id')}",
                       "Remote" + (f" (office: {loc.get('country')})" if loc.get("country") else ""), None,
                       (True, "remote, region checked at rank")))
    return out


def zoho(c):
    host = c["slug"] if "." in c["slug"] else f"{c['slug']}.zohorecruit.com"
    page = htmllib.unescape(rb.get(f"https://{host}/jobs/Careers").decode("utf-8", "replace"))
    dec = json.JSONDecoder()
    found = {}
    for m in re.finditer(r'"Job_Opening_Name":"', page):
        # walk back to the opening brace of the job object and decode it
        for start in [i for i in range(m.start(), max(m.start() - 20000, 0), -1) if page[i] == "{"][:60]:
            try:
                obj, _ = dec.raw_decode(page, start)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and obj.get("Job_Opening_Name") and obj.get("id"):
                found[obj["id"]] = obj
                break
    out = []
    for j in found.values():
        if not j.get("Remote_Job") or j.get("Publish") is False:
            continue
        place = ", ".join(x for x in (j.get("City"), j.get("Country")) if x)
        out.append(job(c["name"], j["Job_Opening_Name"], f"https://{host}/jobs/Careers/{j['id']}", place or "Remote",
                       rb.parse_date(j.get("Date_Opened")), region_ok(place) if place else (True, "no region stated")))
    return out


def ats(c):
    out = []
    for j in ats_boards.SYSTEMS[c["ats"]](c["slug"]):
        ok, why = ats_boards.remote_region_ok(j["loc"], S)
        out.append(job(c["name"], j["title"], j["url"], ", ".join(x for x in j["loc"] if x), j["date"], (ok, why)))
    return out


FETCHERS = {"workable": workable, "teamtailor": teamtailor, "manatal": manatal, "bamboohr": bamboohr,
            "zoho": zoho, "greenhouse": ats, "lever": ats, "ashby": ats}


def poll(c):
    try:
        return c, FETCHERS[c["ats"]](c), None
    except Exception as exc:  # noqa: BLE001 - one dead careers page must not stop the run
        return c, [], str(exc)[:160]


def load_list():
    data = json.loads(WATCHLIST.read_text(encoding="utf-8"))
    return [c for c in data.get("companies", []) if c.get("ats") in FETCHERS]


def cmd_poll(args):
    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days or S.max_age_days)
    companies = load_list()
    why, kept, seen, report = Counter(), [], set(), {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for c, jobs, err in pool.map(poll, companies):
            report[c["name"]] = err or len(jobs)
            for j in jobs:
                if not j["url"].startswith("http") or j["url"] in seen:
                    continue
                seen.add(j["url"])
                if rb.keep(j, cutoff, why, S):
                    kept.append({
                        "title": j["title"], "company": j["company"], "url": j["url"], "location": j["location"],
                        "date": j["posted"].date().isoformat() if j["posted"] else None, "salary": j["salary"],
                        "portal": "watchlist", "source": "cli",
                        **({"description": j.get("_desc") or ""} if args.with_description else {}),
                    })
    Path(args.out).write_text(json.dumps(kept, ensure_ascii=False, indent=1), encoding="utf-8")
    errors = {k: v for k, v in report.items() if isinstance(v, str)}
    print(json.dumps({"companies": len(companies), "fetched": len(seen), "kept": len(kept),
                      "errors": errors, **({"per_company": report, "dropped": why} if args.explain else {})},
                     default=dict, indent=1))
    return 0


def cmd_suggest(_args):
    on_list = {c["name"].lower() for c in load_list()}
    seen = json.loads(SEEN.read_text(encoding="utf-8"))["seen"]
    scores = {}
    for v in seen.values():
        try:
            s = float(v.get("rank_score"))
        except (TypeError, ValueError):
            continue
        name = (v.get("company") or "").strip()
        if not name or name.lower() in on_list:
            continue
        scores.setdefault(name, []).append((s, v.get("url", "")))
    # repeat posters only: two or more ranked postings, at least one 70+ or two 60+
    rows = [(n, xs) for n, xs in scores.items()
            if len(xs) >= 2 and (any(s >= 70 for s, _ in xs) or sum(s >= 60 for s, _ in xs) >= 2)]
    rows.sort(key=lambda r: -max(s for s, _ in r[1]))
    for name, xs in rows:
        best = max(xs)
        print(f"{int(best[0]):>3}  {len(xs)} ranked  {name}  {best[1].split('?')[0]}")
    print(f"\n{len(rows)} suggestions. Add the ones worth watching to {WATCHLIST.relative_to(ROOT)} by hand.")
    return 0


def main():
    rb_force = getattr(__import__("rank_state"), "_force_utf8_output", None)
    if rb_force:
        rb_force()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out")
    ap.add_argument("--settings", default=str(search_settings.DEFAULT_PATH))
    ap.add_argument("--days", type=int, default=None, help="default: max_age_days from settings")
    ap.add_argument("--explain", action="store_true")
    ap.add_argument("--with-description", action="store_true")
    ap.add_argument("--suggest", action="store_true")
    args = ap.parse_args()
    if args.suggest:
        return cmd_suggest(args)
    if not args.out:
        ap.error("--out is required unless --suggest")
    global S
    try:
        S = search_settings.load(args.settings)
    except search_settings.SettingsMissing as exc:
        print(exc, file=sys.stderr)
        return 1
    return cmd_poll(args)


if __name__ == "__main__":
    sys.exit(main())
