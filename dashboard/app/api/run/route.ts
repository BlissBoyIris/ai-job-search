import { NextResponse } from "next/server";
import { buildJobs } from "../../../lib/jobs";
import { listRuns, runAnswers, runApply, runRank, runScrape } from "../../../lib/runner";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const id = new URL(req.url).searchParams.get("id");
  const runs = listRuns();
  if (id) {
    const r = runs.find((x) => x.id === id);
    return r ? NextResponse.json(r) : NextResponse.json({ error: "not found" }, { status: 404 });
  }
  return NextResponse.json(runs.map((r) => ({ ...r, lines: r.lines.slice(-1) })));
}

export async function POST(req: Request) {
  const body = await req.json().catch(() => ({}));
  const action = String(body.action ?? "");
  if (action === "scrape") return NextResponse.json(runScrape());
  if (action === "rank") return NextResponse.json(runRank(Number(body.limit) || 20));

  const { jobs } = buildJobs();
  if (action === "prepare") {
    const n = Math.max(1, Math.min(20, Number(body.n) || 5));
    const picks = jobs
      .filter((j) => j.score != null && !j.excluded && !j.app.cv && j.app.applyStatus !== "stopped" && !j.trackerStatus && !(j.applyRun && (j.applyRun.status === "queued" || j.applyRun.status === "running")))
      .slice(0, n);
    return NextResponse.json(picks.map((j) => runApply(j)));
  }

  const job = jobs.find((j) => j.key === body.key);
  if (!job || !job.url) return NextResponse.json({ error: "Unknown job or missing posting URL" }, { status: 400 });
  if (action === "apply") return NextResponse.json(runApply(job));
  if (action === "answers") {
    const q = String(body.questions ?? "").trim();
    if (!q) return NextResponse.json({ error: "Paste the screening questions first" }, { status: 400 });
    if (q.length > 8000) return NextResponse.json({ error: "Too long - paste just the questions" }, { status: 400 });
    return NextResponse.json(runAnswers(job, q));
  }
  return NextResponse.json({ error: "Unknown action" }, { status: 400 });
}
