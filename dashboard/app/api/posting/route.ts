import fs from "node:fs";
import path from "node:path";
import { NextResponse } from "next/server";
import { savePosting } from "../../../lib/claude";
import { slugOf } from "../../../lib/fastapply";
import { buildJobs } from "../../../lib/jobs";
import { REPO, reopenSeen, updateApp } from "../../../lib/repo";
import { activeFor, env, runFastApply } from "../../../lib/runner";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** The user pastes a posting the dashboard could not read: gate and store it, then write the CV and cover letter. */
export async function POST(req: Request) {
  const body = await req.json().catch(() => ({}));
  const text = String(body.text ?? "").trim();
  const job = buildJobs().jobs.find((j) => j.key === body.key);
  if (!job) return NextResponse.json({ error: "Unknown job" }, { status: 400 });
  if (text.length < 300) return NextResponse.json({ error: "Paste the full job description (it looks too short)." }, { status: 400 });
  if (text.length > 30000) return NextResponse.json({ error: "That is too long - paste just the job description." }, { status: 400 });
  if (activeFor("scrape") || activeFor("rank")) {
    return NextResponse.json({ error: "Wait for Scrape / Rank to finish, then paste again." }, { status: 409 });
  }
  try {
    await savePosting(job.key, `${job.title} - ${job.company}\n\n${text}`, env());
  } catch (e) {
    return NextResponse.json({ error: (e as Error).message }, { status: 400 });
  }
  // A posting archived by an earlier run would win over the pasted text, so drop it; the CV run re-archives.
  fs.rmSync(path.join(REPO, "documents", "applications", slugOf(job.company, job.title), "job_posting.md"), { force: true });
  reopenSeen(job.key);
  updateApp(job.key, { applyStatus: undefined, reason: undefined });
  if (body.write === false) return NextResponse.json({ ok: true });
  return NextResponse.json(runFastApply(job));
}
