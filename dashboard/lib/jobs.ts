// Builds the job list the UI shows, joining seen_jobs.json, the tracker and dashboard records.
import { findTrackerRow, readApps, readSeen, readTracker, searchSubtitle, today, type AppRecord } from "./repo";
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

  const jobs: JobView[] = [];
  for (const [key, j] of Object.entries(seen)) {
    if (!["new", "ranked", "unreachable"].includes(j.status)) continue;
    const app = apps[key] ?? {};
    const row =
      (app.trackerCompany && app.trackerRole && findTrackerRow(tracker, app.trackerCompany, app.trackerRole)) ||
      findTrackerRow(tracker, j.company, j.title);
    const excluded = j.location_verdict === "FAIL" || j.language_gate === "FAIL";
    // Weak fit: ranked Weak/Poor, or never ranked and quick-assessed low. Never when documents already exist.
    const weak =
      !app.cv &&
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
      seenStatus: j.status,
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
      trackerStatus: row ? row.status : null,
      trackerDate: row ? row.date || null : null,
      app,
      applyRun: brief(activeFor("apply", key) ?? latest("apply", key)),
      answersRun: brief(activeFor("answers", key) ?? latest("answers", key)),
    });
  }

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
