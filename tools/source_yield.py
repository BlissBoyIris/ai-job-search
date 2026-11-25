#!/usr/bin/env python3
"""Which sources produce good roles? Read-only report over job_scraper/seen_jobs.json.

    python3 tools/source_yield.py [--days 14] [--by host|portal|both]

For each portal (and the posting's URL host) over the last N days of `first_seen`:
new = stored, ranked = has a rank_score, then 60-69 and 70+ counts. A source with
no 60+ after a week of runs is a candidate to drop from queries.json / remote_boards.py.
"""

import argparse
import json
import sys
import urllib.parse
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

SEEN = Path(__file__).resolve().parent.parent / "job_scraper" / "seen_jobs.json"


def score(v):
    try:
        return float(v.get("rank_score"))
    except (TypeError, ValueError):
        return None


def table(rows, label):
    print(f"\n{label:<28} {'new':>5} {'ranked':>7} {'60-69':>6} {'70+':>4}  70+/ranked")
    for name, c in sorted(rows.items(), key=lambda kv: (-kv[1]["70"], -kv[1]["60"], -kv[1]["new"])):
        rate = f"{100 * c['70'] / c['ranked']:.0f}%" if c["ranked"] else "-"
        print(f"{name[:28]:<28} {c['new']:>5} {c['ranked']:>7} {c['60']:>6} {c['70']:>4}  {rate:>6}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--by", choices=("portal", "host", "both"), default="both")
    args = ap.parse_args()
    since = (date.today() - timedelta(days=args.days)).isoformat()
    seen = json.loads(SEEN.read_text(encoding="utf-8"))["seen"]
    portals, hosts = defaultdict(lambda: defaultdict(int)), defaultdict(lambda: defaultdict(int))
    for v in seen.values():
        if (v.get("first_seen") or "") < since:
            continue
        host = urllib.parse.urlparse(v.get("url") or "").netloc.removeprefix("www.")
        host = "linkedin.com" if host.endswith("linkedin.com") else host
        s = score(v)
        for bucket, key in ((portals, v.get("portal") or "?"), (hosts, host or "?")):
            c = bucket[key]
            c["new"] += 1
            if s is not None:
                c["ranked"] += 1
                c["60"] += 60 <= s < 70
                c["70"] += s >= 70
    print(f"Source yield since {since} ({args.days} days)")
    if args.by in ("portal", "both"):
        table(portals, "portal")
    if args.by in ("host", "both"):
        table({k: v for k, v in hosts.items() if v["ranked"]}, "posting host (ranked only)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
