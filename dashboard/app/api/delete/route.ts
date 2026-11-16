import { NextResponse } from "next/server";
import { buildJobs } from "../../../lib/jobs";
import { skipJobs } from "../../../lib/repo";
import { activeFor } from "../../../lib/runner";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** Remove open jobs from the list by marking them `skipped` in seen_jobs.json (the repo's own "never show again" state). */
export async function POST(req: Request) {
  const body = await req.json().catch(() => ({}));
  let keys: string[] = Array.isArray(body.keys) ? body.keys.map(String) : [];
  if (body.weak === true) {
    // Server-side definition of "weak fit" (see lib/jobs.ts); excluded jobs are left in their own list.
    keys = buildJobs().jobs.filter((j) => j.weak && !j.excluded && !j.trackerStatus).map((j) => j.key);
  }
  if (keys.length === 0) return NextResponse.json({ error: "Nothing selected" }, { status: 400 });
  if (activeFor("scrape") || activeFor("rank")) {
    return NextResponse.json({ error: "Wait for Scrape / Rank to finish, then delete." }, { status: 409 });
  }
  // Only open jobs: never delete something already applied.
  const open = new Set(
    buildJobs().jobs.filter((j) => !j.trackerStatus || j.trackerStatus === "drafted").map((j) => j.key),
  );
  const allowed = keys.filter((k) => open.has(k));
  const n = skipJobs(allowed);
  return NextResponse.json({ ok: true, deleted: n });
}
