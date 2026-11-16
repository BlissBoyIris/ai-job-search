// Server-only helpers: read the AIJS repo's state files and the dashboard's own store.
import fs from "node:fs";
import path from "node:path";

export const REPO = path.resolve(process.cwd(), "..");
export const DATA_DIR = path.join(process.cwd(), ".data");
const SEEN = path.join(REPO, "job_scraper", "seen_jobs.json");
const TRACKER = path.join(REPO, "job_search_tracker.csv");
const APPS = path.join(DATA_DIR, "apps.json");

const TRACKER_HEADER =
  "date,company,sector,role,role_type,channel,status,contact_person,fit_rating,notes,cv_file,cover_letter_file,source,deadline";

export type SeenJob = {
  title: string;
  company: string;
  url: string;
  location?: string | null;
  posted_date?: string | null;
  deadline?: string | null;
  fit?: string;
  status: string;
  portal?: string;
  rank_score?: number;
  rank_verdict?: string;
  location_verdict?: string;
  language_gate?: string;
  language_note?: string;
  strengths?: string[];
  gaps?: string[];
  guard?: string;
  last_fetch_error?: string;
};

export type AppRecord = {
  cv?: string;
  cover?: string;
  verdict?: string;
  score?: number;
  reason?: string;
  applyStatus?: "done" | "stopped" | "failed";
  trackerCompany?: string;
  trackerRole?: string;
  answers?: { q: string; a: string }[];
  appliedAt?: string;
};

export type TrackerRow = Record<string, string>;

function ensureDataDir() {
  fs.mkdirSync(DATA_DIR, { recursive: true });
}

export function today(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function readSeen(): Record<string, SeenJob> {
  try {
    return JSON.parse(fs.readFileSync(SEEN, "utf8")).seen ?? {};
  } catch {
    return {};
  }
}

export function readApps(): Record<string, AppRecord> {
  try {
    return JSON.parse(fs.readFileSync(APPS, "utf8"));
  } catch {
    return {};
  }
}

export function updateApp(key: string, patch: Partial<AppRecord>) {
  ensureDataDir();
  const apps = readApps();
  apps[key] = { ...(apps[key] ?? {}), ...patch };
  const tmp = APPS + ".tmp";
  fs.writeFileSync(tmp, JSON.stringify(apps, null, 2));
  fs.renameSync(tmp, APPS);
}

// Minimal CSV handling. The repo's writers never emit quoted fields, but tolerate them on read.
function parseLine(line: string): string[] {
  const out: string[] = [];
  let cur = "";
  let q = false;
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (q) {
      if (c === '"' && line[i + 1] === '"') { cur += '"'; i++; }
      else if (c === '"') q = false;
      else cur += c;
    } else if (c === '"') q = true;
    else if (c === ",") { out.push(cur); cur = ""; }
    else cur += c;
  }
  out.push(cur);
  return out;
}

function readTrackerRaw(): { header: string[]; rows: string[][] } {
  if (!fs.existsSync(TRACKER)) return { header: TRACKER_HEADER.split(","), rows: [] };
  const lines = fs.readFileSync(TRACKER, "utf8").split(/\r?\n/).filter((l) => l.trim() !== "");
  if (lines.length === 0) return { header: TRACKER_HEADER.split(","), rows: [] };
  return { header: parseLine(lines[0]), rows: lines.slice(1).map(parseLine) };
}

export function readTracker(): TrackerRow[] {
  const { header, rows } = readTrackerRaw();
  return rows.map((r) => Object.fromEntries(header.map((h, i) => [h, r[i] ?? ""])));
}

const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

export function findTrackerRow(rows: TrackerRow[], company: string, role: string): TrackerRow | undefined {
  const c = norm(company), r = norm(role);
  return rows.find((row) => norm(row.company) === c && norm(row.role) === r);
}

const clean = (s: string) => s.replace(/[,"\r\n]+/g, " ").trim();

/** Mark a job applied: update its open tracker row, or append a new one. Never touches other rows. */
export function markApplied(opts: { company: string; role: string; url: string; cv?: string; cover?: string; score?: number }) {
  const { header, rows } = readTrackerRaw();
  const idx = (name: string) => header.indexOf(name);
  const d = today();
  const c = norm(opts.company), r = norm(opts.role);
  const FINAL = new Set(["hired", "rejected", "no_response", "no response", "offer_declined", "offer declined", "withdrawn"]);
  const match = rows.findIndex(
    (row) => norm(row[idx("company")] ?? "") === c && norm(row[idx("role")] ?? "") === r && !FINAL.has((row[idx("status")] ?? "").toLowerCase()),
  );
  if (match >= 0) {
    const row = rows[match];
    while (row.length < header.length) row.push("");
    row[idx("status")] = "applied";
    row[idx("date")] = d;
    const notes = row[idx("notes")] ?? "";
    row[idx("notes")] = clean(`${notes} applied via dashboard ${d}`);
  } else {
    const row = header.map(() => "");
    const set = (k: string, v: string) => { if (idx(k) >= 0) row[idx(k)] = clean(v); };
    set("date", d);
    set("company", opts.company);
    set("role", opts.role);
    set("channel", "online");
    set("status", "applied");
    set("fit_rating", opts.score != null ? String(Math.round(opts.score)) : "");
    set("notes", `applied via dashboard ${d}`);
    set("cv_file", opts.cv ?? "");
    set("cover_letter_file", opts.cover ?? "");
    set("source", opts.url);
    rows.push(row);
  }
  // Quote only fields that need it, so rows written by other tools with commas inside a field survive.
  const field = (v: string) => (/[",\r\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v);
  const body = [header.map(field).join(","), ...rows.map((r2) => r2.map(field).join(","))].join("\n") + "\n";
  const tmp = TRACKER + ".tmp";
  fs.writeFileSync(tmp, body);
  fs.renameSync(tmp, TRACKER);
}

/** Resolve a repo-relative PDF path safely (cv/ or cover_letters/ only). */
export function safePdf(rel: string): string | null {
  const abs = path.resolve(REPO, rel);
  const ok = [path.join(REPO, "cv") + path.sep, path.join(REPO, "cover_letters") + path.sep].some((p) => abs.startsWith(p));
  if (!ok || !abs.endsWith(".pdf") || !fs.existsSync(abs)) return null;
  return abs;
}

/** Mark seen jobs as `skipped` so they leave the dashboard and the scraper never re-adds them. Returns how many changed. */
export function skipJobs(keys: string[]): number {
  let doc: { seen?: Record<string, SeenJob & Record<string, unknown>> };
  try {
    doc = JSON.parse(fs.readFileSync(SEEN, "utf8"));
  } catch {
    return 0;
  }
  const seen = doc.seen ?? {};
  let n = 0;
  for (const k of keys) {
    if (seen[k] && seen[k].status !== "skipped") {
      seen[k].status = "skipped";
      seen[k].skipped_by = "dashboard";
      n++;
    }
  }
  if (n === 0) return 0;
  const tmp = SEEN + ".tmp";
  fs.writeFileSync(tmp, JSON.stringify(doc, null, 2) + "\n");
  fs.renameSync(tmp, SEEN);
  return n;
}

// One line describing the user's search, built from my_search.json (written by /start).
export function searchSubtitle(): string {
  try {
    const s = JSON.parse(fs.readFileSync(path.join(REPO, "my_search.json"), "utf8")) as {
      roles?: string[];
      work_mode?: string;
      pay_floor?: { amount?: number; currency?: string; per?: string };
    };
    const roles = (s.roles ?? []).filter(Boolean);
    if (!roles.length) return "Run /start to set up your search.";
    const mode = { remote: "Remote", hybrid: "Hybrid", onsite: "On-site" }[s.work_mode ?? ""] ?? "";
    const shown = roles.slice(0, 3).join(", ") + (roles.length > 3 ? " and more" : "");
    let line = `${mode ? mode + " " : ""}${shown} roles`;
    const f = s.pay_floor;
    if (f?.amount && f.currency) line += `, ${f.currency} ${f.amount.toLocaleString("en-US")} per ${f.per ?? "year"} and up`;
    return line + ".";
  } catch {
    return "Run /start to set up your search.";
  }
}
