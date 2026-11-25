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
  skipped_by?: string;
  expired_reason?: string;
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
  cost?: number;
  /** Saved for later: a good job the user will apply to later. Kept out of bulk delete and auto CV runs. */
  savedAt?: string;
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


// Mirrors tools/rank_state.py company_key/same_role, so the dashboard and /scrape agree on what counts as tracked.
const LEGAL_FORMS = new Set([
  "inc", "llc", "ltd", "limited", "corp", "corporation", "co", "company", "gmbh",
  "pte", "plc", "pvt", "private", "sa", "sas", "bv", "ag", "srl", "oy", "ab", "as",
]);
const MIN_CONTAINED_TITLE = 10;

const companyKey = (s: string) => {
  const words = s.normalize("NFC").toLowerCase().split(/[^\p{L}\p{N}\p{M}]+/u).filter(Boolean);
  while (words.length > 1 && LEGAL_FORMS.has(words[words.length - 1])) words.pop();
  return words.join("");
};
const titleKey = (s: string) => s.normalize("NFC").toLowerCase().replace(/[^\p{L}\p{N}\p{M}]+/gu, "");

/** Same job: equal titles, or one wraps the other ("Head of Growth" vs "Head of Growth / Senior Growth Manager"). */
function sameRole(a: string, b: string): boolean {
  if (a === b) return true;
  const [short, long] = a.length <= b.length ? [a, b] : [b, a];
  return short.length >= MIN_CONTAINED_TITLE && long.includes(short);
}

export function trackerMatch(rowCompany: string, rowRole: string, company: string, role: string): "exact" | "fuzzy" | null {
  if (companyKey(rowCompany) !== companyKey(company)) return null;
  const a = titleKey(rowRole), b = titleKey(role);
  return a === b ? "exact" : sameRole(a, b) ? "fuzzy" : null;
}

export function findTrackerRow(rows: TrackerRow[], company: string, role: string): TrackerRow | undefined {
  return (
    rows.find((row) => trackerMatch(row.company ?? "", row.role ?? "", company, role) === "exact") ??
    rows.find((row) => trackerMatch(row.company ?? "", row.role ?? "", company, role) === "fuzzy")
  );
}

const clean = (s: string) => s.replace(/[,"\r\n]+/g, " ").trim();

/** Mark a job applied: update its open tracker row, or append a new one. Never touches other rows. */
export function markApplied(opts: { company: string; role: string; url: string; cv?: string; cover?: string; score?: number }) {
  const { header, rows } = readTrackerRaw();
  const idx = (name: string) => header.indexOf(name);
  const d = today();
  const FINAL = new Set(["hired", "rejected", "no_response", "no response", "offer_declined", "offer declined", "withdrawn"]);
  const open = (row: string[], kind: "exact" | "fuzzy") =>
    trackerMatch(row[idx("company")] ?? "", row[idx("role")] ?? "", opts.company, opts.role) === kind &&
    !FINAL.has((row[idx("status")] ?? "").toLowerCase());
  let match = rows.findIndex((row) => open(row, "exact"));
  if (match < 0) match = rows.findIndex((row) => open(row, "fuzzy"));
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
  writeTrackerRaw(header, rows);
}

/** Record drafted documents: fill the open row for this job (exact, then repost match), or append a drafted row. */
export function upsertDrafted(opts: { company: string; role: string; url: string; score?: number; notes: string; cvTex: string; coverTex: string }) {
  const { header, rows } = readTrackerRaw();
  const idx = (name: string) => header.indexOf(name);
  const find = (kind: "exact" | "fuzzy") =>
    rows.findIndex((row) => trackerMatch(row[idx("company")] ?? "", row[idx("role")] ?? "", opts.company, opts.role) === kind);
  let match = find("exact");
  if (match < 0) match = find("fuzzy");
  const row = match >= 0 ? rows[match] : header.map(() => "");
  while (row.length < header.length) row.push("");
  const set = (k: string, v: string) => { if (idx(k) >= 0) row[idx(k)] = clean(v); };
  set("cv_file", opts.cvTex);
  set("cover_letter_file", opts.coverTex);
  if (match < 0) {
    set("date", today());
    set("company", opts.company);
    set("role", opts.role);
    set("role_type", "Full Time");
    set("channel", "online");
    set("status", "drafted");
    set("fit_rating", opts.score != null ? String(Math.round(opts.score)) : "");
    set("notes", opts.notes);
    set("source", opts.url);
    rows.push(row);
  }
  writeTrackerRaw(header, rows);
}

function writeTrackerRaw(header: string[], rows: string[][]) {
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

/** Deleted on the dashboard (Delete / Remove weak fits). Never shown or re-added again. */
export const isDeleted = (j: { status?: string; skipped_by?: string }) => j.status === "skipped" && j.skipped_by === "dashboard";

const OPEN = new Set(["new", "ranked", "unreachable"]);

/** Delete jobs: mark them `skipped` (by dashboard) in seen_jobs.json so the scraper and ranker never bring them back.
 *  Open copies of the same job (a board repost under a variant title) go too, unless `protect` holds them. */
export function skipJobs(keys: string[], protect: Set<string> = new Set()): number {
  let doc: { seen?: Record<string, SeenJob & Record<string, unknown>> };
  try {
    doc = JSON.parse(fs.readFileSync(SEEN, "utf8"));
  } catch {
    return 0;
  }
  const seen = doc.seen ?? {};
  const removed = keys.filter((k) => seen[k]).map((k) => seen[k]);
  let n = 0;
  const skip = (k: string, reason?: string) => {
    if (seen[k].status === "skipped" && seen[k].skipped_by === "dashboard") return;
    seen[k].status = "skipped";
    seen[k].skipped_by = "dashboard";
    if (reason) seen[k].skipped_reason = reason;
    n++;
  };
  for (const k of keys) if (seen[k]) skip(k);
  for (const [k, j] of Object.entries(seen)) {
    if (!OPEN.has(j.status) || protect.has(k)) continue;
    if (removed.some((r) => trackerMatch(r.company ?? "", r.title ?? "", j.company ?? "", j.title ?? ""))) {
      skip(k, "repost of a deleted job");
    }
  }
  if (n === 0) return 0;
  const tmp = SEEN + ".tmp";
  fs.writeFileSync(tmp, JSON.stringify(doc, null, 2) + "\n");
  fs.renameSync(tmp, SEEN);
  return n;
}

/** A job whose page could not be read, now that the user supplied the posting: back to `new` so it shows as a
 *  normal job and /rank scores it from the pasted text. Drops the failed-fetch bookkeeping. */
export function reopenSeen(key: string) {
  let doc: { seen?: Record<string, SeenJob & Record<string, unknown>> };
  try { doc = JSON.parse(fs.readFileSync(SEEN, "utf8")); } catch { return; }
  const j = doc.seen?.[key];
  if (!j) return;
  const gaveUp = j.status === "expired" && j.expired_reason === "unreachable";
  if (j.status !== "unreachable" && !gaveUp) return;
  j.status = "new";
  for (const f of ["fetch_attempts", "first_unreachable", "last_fetch_error", "expired_reason"]) delete j[f];
  const tmp = SEEN + ".tmp";
  fs.writeFileSync(tmp, JSON.stringify(doc, null, 2) + "\n");
  fs.renameSync(tmp, SEEN);
}

/** Save jobs for later, or move them back to Open. */
export function setSaved(keys: string[], saved: boolean) {
  for (const k of keys) updateApp(k, { savedAt: saved ? today() : undefined });
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
