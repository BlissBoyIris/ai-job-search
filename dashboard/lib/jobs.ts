// Builds the job list the UI shows, joining seen_jobs.json, the tracker and dashboard records.
import { hasPosting } from "./claude";
import { findTrackerRow, isDeleted, readApps, readSeen, readTracker, searchSubtitle, today, trackerMatch, type AppRecord, type TrackerRow } from "./repo";
import { activeFor, listRuns, type Run } from "./runner";

export type JobView = {
  key: string;
  title: string;
  company: string;
  url: string;
  location: string;
  posted: string | null;
  fit: string | null;
  seenStatus: string;
  score: number | null;
  verdict: string | null;
  locationVerdict: string | null;
  languageGate: string | null;
  languageNote: string | null;
  strengths: string[];
  gaps: string[];
  guard: string | null;
  fetchError: string | null;
  excluded: boolean;
  weak: boolean;
  saved: boolean;
  /** The page could not be read and no posting text is on file: the user can paste it. */
  needsPosting: boolean;
  trackerStatus: string | null;
  trackerDate: string | null;
  app: AppRecord;
  applyRun: RunBrief | null;
  answersRun: RunBrief | null;
};

export type RunBrief = { id: string; status: Run["status"]; last: string; startedAt?: number; endedAt?: number };

const brief = (r?: Run): RunBrief | null =>
  r ? { id: r.id, status: r.status, last: r.lines[r.lines.length - 1] ?? "", startedAt: r.startedAt, endedAt: r.endedAt } : null;

export function buildJobs() {
  const seen = readSeen();
  const apps = readApps();
  const tracker = readTracker();
  const runs = listRuns();
  const latest = (kind: Run["kind"], key: string) => runs.find((r) => r.kind === kind && r.key === key);

  const deleted = Object.values(seen).filter(isDeleted);
  const jobs: JobView[] = [];
  for (const [key, j] of Object.entries(seen)) {
    const app = apps[key] ?? {};
    const saved = !!app.savedAt;
    // Saved jobs stay visible after the posting closes (shown as Closed); everything else only while open.
    // Jobs /rank gave up on (page never readable) stay listed so the posting can be pasted in.
    const gaveUp = j.status === "expired" && j.expired_reason === "unreachable";
    if (!["new", "ranked", "unreachable"].includes(j.status) && !(saved && j.status === "expired") && !gaveUp) continue;
    const row =
      (app.trackerCompany && app.trackerRole && findTrackerRow(tracker, app.trackerCompany, app.trackerRole)) ||
      findTrackerRow(tracker, j.company, j.title);
    // A repost of a job the user deleted stays hidden, unless they saved or applied to this copy.
    const sent = !!row && row.status !== "drafted";
    if (!saved && !sent && deleted.some((d) => trackerMatch(d.company ?? "", d.title ?? "", j.company ?? "", j.title ?? ""))) continue;
    const excluded = j.location_verdict === "FAIL" || j.language_gate === "FAIL";
    // Weak fit: ranked Weak/Poor, or never ranked and quick-assessed low. Never when documents already exist.
    const weak =
      !app.cv && !saved &&
      (j.rank_verdict === "Weak Fit" || j.rank_verdict === "Poor Fit" ||
        (typeof j.rank_score !== "number" && j.fit === "low" && j.status === "new"));
    jobs.push({
      key,
      title: j.title,
      company: j.company,
      url: /^https?:\/\//.test(j.url) ? j.url.replace(/[?&]utm_source=freehire\.me$/, "") : "",
      location: j.location ?? "",
      posted: j.posted_date ?? null,
      fit: j.fit ?? null,
      seenStatus: gaveUp ? "unreachable" : j.status,
      score: typeof j.rank_score === "number" ? j.rank_score : null,
      verdict: j.rank_verdict ?? null,
      locationVerdict: j.location_verdict ?? null,
      languageGate: j.language_gate ?? null,
      languageNote: j.language_note ?? null,
      strengths: j.strengths ?? [],
      gaps: j.gaps ?? [],
      guard: j.guard && j.guard !== "clean" && !j.guard.includes(": clean") ? j.guard : null,
      fetchError: j.last_fetch_error ?? null,
      excluded,
      weak,
      saved,
      needsPosting:
        !sent && !hasPosting(key) &&
        (j.status === "unreachable" || gaveUp || (app.applyStatus === "failed" && /readable|read the posting/i.test(app.reason ?? ""))),
      trackerStatus: row ? row.status : null,
      trackerDate: row ? row.date || null : null,
      app,
      applyRun: brief(activeFor("apply", key) ?? latest("apply", key)),
      answersRun: brief(activeFor("answers", key) ?? latest("answers", key)),
    });
  }

  // A board repost of a job already in the tracker joins that row. Show one job per sent application:
  // the one with documents or an exact title wins, the reposts are dropped from both lists.
  const rowOf = new Map<JobView, TrackerRow>();
  for (const job of jobs) {
    const app = job.app;
    const row =
      (app.trackerCompany && app.trackerRole && findTrackerRow(tracker, app.trackerCompany, app.trackerRole)) ||
      findTrackerRow(tracker, job.company, job.title);
    if (row && row.status !== "drafted") rowOf.set(job, row);
  }
  const owner = new Map<TrackerRow, JobView>();
  const weight = (job: JobView, row: TrackerRow) =>
    (job.app.cv ? 2 : 0) + (trackerMatch(row.company ?? "", row.role ?? "", job.company, job.title) === "exact" ? 1 : 0);
  for (const [job, row] of rowOf) {
    const cur = owner.get(row);
    if (!cur || weight(job, row) > weight(cur, row)) owner.set(row, job);
  }
  const dropped = new Set([...rowOf].filter(([job, row]) => owner.get(row) !== job).map(([job]) => job));
  for (let i = jobs.length - 1; i >= 0; i--) if (dropped.has(jobs[i])) jobs.splice(i, 1);

  const fitRank = (f: string | null) => (f === "high" ? 2 : f === "medium" ? 1 : 0);
  jobs.sort((a, b) => {
    const as = a.score ?? -1, bs = b.score ?? -1;
    if (as !== bs) return bs - as;
    if (fitRank(a.fit) !== fitRank(b.fit)) return fitRank(b.fit) - fitRank(a.fit);
    return (b.posted ?? "").localeCompare(a.posted ?? "");
  });

  const d = today();
  const appliedToday = tracker.filter((r) => r.status === "applied" && r.date === d).length;
  const top = (kind: Run["kind"]) => brief(activeFor(kind) ?? runs.find((r) => r.kind === kind));
  return { jobs, appliedToday, scrape: top("scrape"), rank: top("rank"), subtitle: searchSubtitle() };
}
