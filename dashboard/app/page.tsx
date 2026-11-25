"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { JobView, RunBrief } from "../lib/jobs";

type Data = { jobs: JobView[]; appliedToday: number; scrape: RunBrief | null; rank: RunBrief | null; subtitle?: string };

const GOAL = 20;
const busy = (r: RunBrief | null) => !!r && (r.status === "queued" || r.status === "running");

function DocIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden>
      <path d="M4 1.5h5.5L13 5v9.5H4z" /><path d="M9.5 1.5V5H13" />
    </svg>
  );
}
function ArrowIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" width="12" height="12" aria-hidden>
      <path d="M5 11L11 5M6 5h5v5" />
    </svg>
  );
}

function statusTag(j: JobView) {
  const t = (j.trackerStatus ?? "").toLowerCase();
  if (t && t !== "drafted") return <span className="tag green">{t.replace("_", " ")}</span>;
  if (busy(j.applyRun)) return <span className="tag yellow"><span className="dot" />Writing</span>;
  if (j.seenStatus === "expired") return <span className="tag red">Closed</span>;
  if (j.app.cv) return <span className="tag blue">Docs ready</span>;
  if (j.app.applyStatus === "stopped") return <span className="tag red">Skipped</span>;
  if (j.app.applyStatus === "failed") return <span className="tag red">Failed</span>;
  if (j.needsPosting) return <span className="tag yellow">Paste posting</span>;
  if (j.seenStatus === "unreachable") return <span className="tag gray">Can&apos;t open</span>;
  if (j.verdict) return <span className="tag gray">{j.verdict}</span>;
  return <span className="tag gray">{j.fit ? `New · ${j.fit}` : "New"}</span>;
}

function flags(j: JobView) {
  const out: string[] = [];
  if (j.locationVerdict === "FLAG") out.push("check location");
  if (j.languageGate === "FLAG") out.push("language");
  if (j.guard) out.push("posting flagged");
  return out;
}

export default function Page() {
  const [data, setData] = useState<Data | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [questions, setQuestions] = useState<Record<string, string>>({});
  const [postings, setPostings] = useState<Record<string, string>>({});
  const [prepareN, setPrepareN] = useState(5);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const [checked, setChecked] = useState<Set<string>>(new Set());

  const load = useCallback(async () => {
    try {
      const r = await fetch("/api/jobs", { cache: "no-store" });
      setData(await r.json());
    } catch {
      /* dev server restarting */
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [load]);

  const post = async (url: string, body: object) => {
    setError(null);
    const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) setError(j.error ?? "Something went wrong");
    load();
    return j;
  };

  const jobs = data?.jobs ?? [];
  const isApplied = (j: JobView) => !!j.trackerStatus && j.trackerStatus !== "drafted";
  const main = useMemo(() => jobs.filter((j) => !j.saved && !j.excluded && !isApplied(j)), [jobs]);
  const excluded = useMemo(() => jobs.filter((j) => !j.saved && j.excluded && !isApplied(j)), [jobs]);
  const savedJobs = useMemo(() => jobs.filter((j) => j.saved && !isApplied(j)), [jobs]);
  const appliedJobs = useMemo(
    () => jobs.filter(isApplied).sort((a, b) => (b.trackerDate ?? "").localeCompare(a.trackerDate ?? "")),
    [jobs],
  );
  const job = jobs.find((j) => j.key === sel) ?? null;
  const selected = main.filter((j) => checked.has(j.key));
  const toggle = (k: string) => setChecked((c) => { const n = new Set(c); n.has(k) ? n.delete(k) : n.add(k); return n; });
  const toggleAll = () => setChecked(selected.length === main.length ? new Set() : new Set(main.map((j) => j.key)));
  const deleteSelected = async () => {
    if (selected.length === 0) return;
    if (!window.confirm(`Delete ${selected.length} open job${selected.length === 1 ? "" : "s"}? They won't come back on the next scrape.`)) return;
    const keys = selected.map((j) => j.key);
    const j = await post("/api/delete", { keys });
    if (j.ok) {
      setChecked(new Set());
      if (sel && keys.includes(sel)) setSel(null);
    }
  };
  const saveSelected = async () => {
    if (selected.length === 0) return;
    const j = await post("/api/save", { keys: selected.map((x) => x.key), saved: true });
    if (j.ok) setChecked(new Set());
  };
  const weakJobs = main.filter((j) => j.weak);
  const removeWeak = async () => {
    if (weakJobs.length === 0) return;
    if (!window.confirm(`Remove ${weakJobs.length} weak-fit job${weakJobs.length === 1 ? "" : "s"}? (Weak/Poor ranked fits and unranked low fits. Jobs with documents are kept.) They won't come back on the next scrape.`)) return;
    const j = await post("/api/delete", { weak: true });
    if (j.ok) {
      setChecked(new Set());
      if (sel && weakJobs.some((w) => w.key === sel)) setSel(null);
    }
  };
  const unranked = main.filter((j) => j.score == null && j.seenStatus !== "unreachable").length;
  const applied = data?.appliedToday ?? 0;

  const copy = async (text: string, id: string) => {
    await navigator.clipboard.writeText(text);
    setCopied(id);
    setTimeout(() => setCopied(null), 1200);
  };

  const topStatus = (label: string, r: RunBrief | null) => {
    if (!r) return null;
    if (busy(r)) return `${label}: ${r.last || "starting..."}`;
    if (r.status === "failed") return `${label} failed: ${r.last}`;
    return `${label} finished`;
  };
  const line = topStatus("Rank", data?.rank ?? null) ?? topStatus("Scrape", data?.scrape ?? null);

  return (
    <main className="shell">
      <header className="top">
        <div>
          <h1 className="title">Job Desk</h1>
          <p className="subtitle">{data?.subtitle ?? "Loading your search..."}</p>
        </div>
        <div className="counter">
          <div className="num">{applied}<span> / {GOAL}</span></div>
          <div className="subtitle" style={{ margin: 0 }}>applied today</div>
          <div className="bar"><div style={{ width: `${Math.min(100, (applied / GOAL) * 100)}%` }} /></div>
        </div>
      </header>

      <div className="actions">
        <button className="btn" disabled={busy(data?.scrape ?? null)} onClick={() => post("/api/run", { action: "scrape" })}>
          {busy(data?.scrape ?? null) ? "Scraping..." : "Scrape"}
        </button>
        <button className="btn ghost" disabled={busy(data?.scrape ?? null)} title="Also runs the wider LinkedIn queries (broad_runs in job_scraper/queries.json)" onClick={() => post("/api/run", { action: "scrape", broad: true })}>
          Broad
        </button>
        <button className="btn" disabled={busy(data?.rank ?? null)} onClick={() => post("/api/run", { action: "rank", limit: 100 })}>
          {busy(data?.rank ?? null) ? "Ranking..." : `Rank${unranked ? ` (${unranked} new)` : ""}`}
        </button>
        <span style={{ width: 12 }} />
        <button className="btn ghost" onClick={() => post("/api/run", { action: "prepare", n: prepareN })}>
          Write CVs for top
        </button>
        <input className="num-input" type="number" min={1} max={50} value={prepareN} onChange={(e) => setPrepareN(Number(e.target.value) || 1)} />
        {line && <span className="status-line">{busy(data?.rank ?? null) || busy(data?.scrape ?? null) ? <span className="dot" /> : null}{line}</span>}
      </div>
      {error && <div className="err" style={{ marginBottom: 12 }}>{error}</div>}

      <div className="grid">
        <div className="lists">
        <section className="card">
          <div className="section-head">
            <h2>Open</h2>
            <span className="job-co" style={{ display: "flex", alignItems: "center", gap: 10 }}>
              {main.length} jobs · {main.filter((j) => j.app.cv).length} with documents
              {weakJobs.length > 0 && (
                <button className="btn ghost small" onClick={removeWeak}>Remove weak fits ({weakJobs.length})</button>
              )}
              {selected.length > 0 && (
                <>
                  <button className="btn ghost small" onClick={() => setChecked(new Set())}>Clear</button>
                  <button className="btn ghost small" onClick={saveSelected}>Save {selected.length} for later</button>
                  <button className="btn small danger" onClick={deleteSelected}>Delete {selected.length}</button>
                </>
              )}
            </span>
          </div>
          {!data ? (
            <div className="empty">Loading...</div>
          ) : main.length === 0 ? (
            <div className="empty">No jobs yet. Press Scrape to find some.</div>
          ) : (
            <JobTable rows={main} sel={sel} setSel={setSel} checked={checked} toggle={toggle} toggleAll={toggleAll} />
          )}
          {excluded.length > 0 && (
            <details className="excluded" style={{ borderTop: "1px solid var(--line)" }}>
              <summary>{excluded.length} excluded (not remote for you, pay or language)</summary>
              <table className="table">
                <tbody>
                  {excluded.map((j) => (
                    <tr key={j.key} className="row" onClick={() => setSel(j.key)}>
                      <td className="score">{j.score ?? "-"}</td>
                      <td><div className="job-title">{j.title}</div><div className="job-co">{j.company}</div></td>
                      <td className="job-co">{j.gaps[0] ?? j.languageNote ?? ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          )}
        </section>

        <section className="card">
          <div className="section-head">
            <h2>Saved for later</h2>
            <span className="job-co">{savedJobs.length} good jobs to fill in later</span>
          </div>
          {!data ? (
            <div className="empty">Loading...</div>
          ) : savedJobs.length === 0 ? (
            <div className="empty">Nothing saved. Tick jobs in Open and press Save for later, or use the button on a job.</div>
          ) : (
            <JobTable rows={savedJobs} sel={sel} setSel={setSel} />
          )}
        </section>

        <section className="card">
          <div className="section-head">
            <h2>Applied</h2>
            <span className="job-co">{appliedJobs.length} sent</span>
          </div>
          {!data ? (
            <div className="empty">Loading...</div>
          ) : appliedJobs.length === 0 ? (
            <div className="empty">Nothing applied yet. Mark a job as applied and it moves here.</div>
          ) : (
            <JobTable rows={appliedJobs} sel={sel} setSel={setSel} applied />
          )}
        </section>
        </div>

        <aside className="card panel">
          {!job ? (
            <div className="empty" style={{ padding: "40px 0" }}>
              Pick a job to see why it fits and get your CV, cover letter and screening answers.
            </div>
          ) : (
            <Panel
              key={job.key}
              job={job}
              questions={questions[job.key] ?? ""}
              setQuestions={(v) => setQuestions((q) => ({ ...q, [job.key]: v }))}
              posting={postings[job.key] ?? ""}
              setPosting={(v) => setPostings((q) => ({ ...q, [job.key]: v }))}
              onPaste={async () => {
                const r = await post("/api/posting", { key: job.key, text: postings[job.key] ?? "" });
                if (r && !r.error) setPostings((q) => ({ ...q, [job.key]: "" }));
              }}
              onApply={() => post("/api/run", { action: "apply", key: job.key })}
              onApplyDeep={() => post("/api/run", { action: "apply_deep", key: job.key })}
              onAnswers={() => post("/api/run", { action: "answers", key: job.key, questions: questions[job.key] ?? "" })}
              onApplied={() => post("/api/applied", { key: job.key })}
              onSave={(saved) => post("/api/save", { keys: [job.key], saved })}
              copy={copy}
              copied={copied}
            />
          )}
        </aside>
      </div>
    </main>
  );
}

function JobTable({ rows, sel, setSel, applied, checked, toggle, toggleAll }: {
  rows: JobView[]; sel: string | null; setSel: (k: string) => void; applied?: boolean;
  checked?: Set<string>; toggle?: (k: string) => void; toggleAll?: () => void;
}) {
  const selectable = !applied && !!checked && !!toggle;
  const all = selectable && rows.length > 0 && rows.every((j) => checked!.has(j.key));
  return (
    <table className="table">
      <thead>
        <tr>
          {selectable && <th className="check"><input type="checkbox" aria-label="Select all" checked={all} onChange={toggleAll} /></th>}
          <th>Score</th><th>Role</th><th>Where</th><th>{applied ? "Applied" : "Status"}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((j, i) => (
          <tr key={j.key} className={`row ${sel === j.key ? "active" : ""} ${applied ? "done" : ""}`} style={{ ["--i" as string]: Math.min(i, 30) }} onClick={() => setSel(j.key)}>
            {selectable && (
              <td className="check" onClick={(e) => e.stopPropagation()}>
                <input type="checkbox" aria-label={`Select ${j.title}`} checked={checked!.has(j.key)} onChange={() => toggle!(j.key)} />
              </td>
            )}
            <td className={`score ${j.score == null ? "none" : ""}`}>{j.score ?? "-"}</td>
            <td>
              <div className="job-title">{j.title}</div>
              <div className="job-co">{j.company}{!applied && flags(j).length ? ` · ${flags(j).join(" · ")}` : ""}</div>
            </td>
            <td className="job-co">{j.location || "-"}</td>
            <td>{applied ? <><span className="tag green">{(j.trackerStatus ?? "").replace("_", " ")}</span><div className="job-co">{j.trackerDate ?? ""}</div></> : statusTag(j)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Panel(props: {
  job: JobView;
  questions: string;
  setQuestions: (v: string) => void;
  posting: string;
  setPosting: (v: string) => void;
  onPaste: () => void;
  onApply: () => void;
  onApplyDeep: () => void;
  onAnswers: () => void;
  onApplied: () => void;
  onSave: (saved: boolean) => void;
  copy: (text: string, id: string) => void;
  copied: string | null;
}) {
  const { job: j } = props;
  const writing = busy(j.applyRun);
  const answering = busy(j.answersRun);
  const applied = !!j.trackerStatus && j.trackerStatus !== "drafted";
  const allAnswers = (j.app.answers ?? []).map((x) => `${x.q}\n${x.a}`).join("\n\n");
  const pasteLen = props.posting.trim().length;
  const pasteBox = (
    <>
      <textarea
        placeholder="Paste the full job description here: title, what you'd do, requirements, location/remote terms, pay if listed."
        value={props.posting}
        onChange={(e) => props.setPosting(e.target.value)}
        rows={8}
      />
      <button className="btn block" style={{ marginTop: 6 }} disabled={writing || pasteLen < 300} onClick={props.onPaste}>
        {pasteLen < 300 ? `Paste the posting (${pasteLen}/300 characters minimum)` : "Use this posting and write CV + cover letter"}
      </button>
    </>
  );

  return (
    <div>
      <h3>{j.title}</h3>
      <div className="meta">
        {j.company}{j.location ? ` · ${j.location}` : ""}{j.posted ? ` · posted ${j.posted}` : ""}
      </div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 16 }}>
        {j.score != null && <span className="tag gray">{j.score} · {j.verdict}</span>}
        {j.locationVerdict === "PASS" && <span className="tag green">Remote OK</span>}
        {j.locationVerdict === "FLAG" && <span className="tag yellow">Check location</span>}
        {j.locationVerdict === "FAIL" && <span className="tag red">Location / pay fail</span>}
        {j.languageGate === "FAIL" && <span className="tag red">Language</span>}
        {j.url && (
          <a className="file" href={j.url} target="_blank" rel="noopener noreferrer">Open posting <ArrowIcon /></a>
        )}
      </div>
      {!applied && (
        <button className="btn ghost block" style={{ marginBottom: 12 }} onClick={() => props.onSave(!j.saved)}>
          {j.saved ? `Saved ${j.app.savedAt ?? ""} · move back to Open` : "Save for later (good job, fill in later)"}
        </button>
      )}
      {j.seenStatus === "expired" && <div className="warn">This posting has closed since you saved it.</div>}
      {j.guard && <div className="warn">Posting check: {j.guard}</div>}

      {(j.strengths.length > 0 || j.gaps.length > 0) && (
        <div className="step">
          <div className="step-label">Fit</div>
          <ul className="list">{j.strengths.map((s, i) => <li key={i}>{s}</li>)}</ul>
          {j.gaps.length > 0 && <ul className="list gaps" style={{ marginTop: 8 }}>{j.gaps.map((s, i) => <li key={i}>{s}</li>)}</ul>}
        </div>
      )}
      {j.score == null && j.seenStatus === "new" && (
        <div className="step"><div className="note">Not ranked yet. Press Rank to score it, or go straight to documents.</div></div>
      )}

      <div className="step">
        <div className="step-label"><b>1</b> CV and cover letter</div>
        {j.needsPosting && !writing ? (
          <>
            <div className="warn">
              Couldn&apos;t read this posting page{j.fetchError ? ` (${j.fetchError})` : ""}. Open the posting, copy the whole job
              description, paste it below, and I&apos;ll write the CV and cover letter from it.
            </div>
            {pasteBox}
          </>
        ) : (
        <button className="btn block" disabled={writing || !j.url} onClick={props.onApply}>
          {writing ? "Writing..." : j.app.cv ? "Rewrite CV and cover letter" : "Write CV and cover letter"}
        </button>
        )}
        {!writing && !j.needsPosting && (
          <details style={{ marginTop: 8 }}>
            <summary className="job-co" style={{ cursor: "pointer" }}>Posting text wrong or missing? Paste it yourself</summary>
            <div style={{ marginTop: 8 }}>{pasteBox}</div>
          </details>
        )}
        {!writing && !j.needsPosting && (
          <button className="btn ghost block" style={{ marginTop: 6 }} disabled={!j.url} onClick={props.onApplyDeep}
            title="The full /apply agent: company research and a reviewer pass. About 5-10 minutes and roughly $2.50 per job.">
            Deep version with research (slow, ~$2.50)
          </button>
        )}
        {writing && j.applyRun?.last && <div className="progress"><span className="dot" />{j.applyRun.last}</div>}
        {j.app.applyStatus === "stopped" && <div className="warn">Stopped before drafting: {j.app.reason}</div>}
        {j.app.applyStatus === "failed" && !writing && <div className="err">{j.app.reason ?? "The run failed."} Try again.</div>}
        {(j.app.cv || j.app.cover) && (
          <>
            <div className="files">
              {j.app.cv && <a className="file" href={`/api/file?path=${encodeURIComponent(j.app.cv)}`} target="_blank" rel="noopener noreferrer"><DocIcon /> CV</a>}
              {j.app.cover && <a className="file" href={`/api/file?path=${encodeURIComponent(j.app.cover)}`} target="_blank" rel="noopener noreferrer"><DocIcon /> Cover letter</a>}
            </div>
            {j.app.reason && <div className="note">{j.app.score != null ? `${j.app.score}/100 · ` : ""}{j.app.reason}</div>}
          </>
        )}
      </div>

      <div className="step">
        <div className="step-label"><b>2</b> Screening questions</div>
        <textarea
          placeholder="Paste the questions from the application form, one per line."
          value={props.questions}
          onChange={(e) => props.setQuestions(e.target.value)}
        />
        <div style={{ marginTop: 8 }}>
          <button className="btn block" disabled={answering || !props.questions.trim()} onClick={props.onAnswers}>
            {answering ? "Writing answers... (1-2 min)" : "Get answers"}
          </button>
        </div>
        {answering && j.answersRun?.last && <div className="progress"><span className="dot" />{j.answersRun.last}</div>}
        {j.answersRun?.status === "failed" && !answering && !(j.app.answers?.length) && <div className="err">Couldn&apos;t produce answers. Try again.</div>}
        {(j.app.answers ?? []).length > 0 && (
          <>
            {(j.app.answers ?? []).map((x, i) => (
              <div className="answer" key={i}>
                <div className="q">{x.q}</div>
                <div className="a">{x.a}</div>
                <div className="row-end">
                  <button className="btn ghost small" onClick={() => props.copy(x.a, `${j.key}-${i}`)}>
                    {props.copied === `${j.key}-${i}` ? "Copied" : "Copy"}
                  </button>
                </div>
              </div>
            ))}
            <div style={{ marginTop: 8 }}>
              <button className="btn ghost small" onClick={() => props.copy(allAnswers, `${j.key}-all`)}>
                {props.copied === `${j.key}-all` ? "Copied" : "Copy all"}
              </button>
            </div>
          </>
        )}
      </div>

      <div className="step" style={{ paddingBottom: 0 }}>
        <div className="step-label"><b>3</b> Submit on the job site, then</div>
        <button className="btn block" disabled={applied} onClick={props.onApplied}>
          {applied ? `Marked ${j.trackerStatus}` : "Mark as applied"}
        </button>
      </div>
    </div>
  );
}
