import { NextResponse } from "next/server";
import { buildJobs } from "../../../lib/jobs";
import { markApplied, today, updateApp } from "../../../lib/repo";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  const body = await req.json().catch(() => ({}));
  const job = buildJobs().jobs.find((j) => j.key === body.key);
  if (!job) return NextResponse.json({ error: "Unknown job" }, { status: 400 });
  markApplied({
    company: job.app.trackerCompany ?? job.company,
    role: job.app.trackerRole ?? job.title,
    url: job.url,
    cv: job.app.cv,
    cover: job.app.cover,
    score: job.app.score ?? job.score ?? undefined,
  });
  updateApp(job.key, { appliedAt: today() });
  return NextResponse.json({ ok: true });
}
