# Friendly first run for a shared copy - design

Date: 2026-11-16

## Why

The owner wants one friend to clone this repo and find jobs with it. Today the
repo holds the owner's own profile in tracked files, and the onboarding
(`/setup`) is long and written for technical people. The friend should open
Claude Code, say anything, and be walked through setup in plain, short
sentences a 16-year-old could follow. Then the search should start.

Success: the friend goes from `git clone` to a ranked list of real jobs in
one sitting, without reading docs, and never sees the owner's personal data.

## Goals

- A private GitHub repo with a clean copy: blank templates, no personal data.
- First run starts by itself when the profile is still blank.
- A new `/start` command that asks, in plain words:
  1. What jobs they want (the kind of work, then job titles).
  2. What they need from a job: remote / hybrid / office, where they live,
     where they can legally work, lowest pay they'd take, deal-breakers.
  3. Their portfolio / website / LinkedIn / GitHub links.
  4. Their CVs and other documents (drop into `documents/`).
- `/start` then hands off to the existing `/setup` (Path A when documents
  were added, Path B for a single pasted CV, Path C if they have nothing),
  passing along the answers so nothing is asked twice.
- After setup, `/start` runs `/scrape` then `/rank` and shows the shortlist,
  with a one-line explanation of what to do next (`/apply <link>`).
- The owner's tools that only fit the owner (`tools/remote_boards.py`,
  `tools/ats_boards.py`, the dashboard) read the friend's answers instead of
  the owner's hardcoded role, region and pay settings.

## Non-goals

- Rewriting `/setup`. It stays as is (it has tests, and upstream updates
  would clash).
- Changing the owner's local working copy. Their `master` and profile files are
  untouched.
- Supporting more than English in the new `/start` wording.

## Anti-goals (failure even if it "works")

- Any of the owner's personal data reaches the pushed repo (name, phone,
  email, work history, pay, application history, tracker, CVs, research).
- The friend hits jargon walls ("LaTeX", "ATS", "frontmatter") without a
  plain explanation, or gets long paragraphs.
- The friend is asked the same thing twice.

## Constraints

- Upstream CI has a placeholder-integrity check (`tests/test_placeholder_integrity.py`,
  `.github/workflows/ci.yml`). The shared copy must keep the template
  placeholders so this keeps passing, and it doubles as a privacy guard.
- `gh` is not installed. The owner has to create the empty private repo (or
  install `gh`), then I push.
- The existing test suite must still pass on the shared branch.

## Approaches

- **A. New `/start` command + auto-trigger in blank `CLAUDE.md` (picked).**
  Keeps `/setup` intact, adds a friendly front door. Small surface.
- B. Rewrite `/setup` in plain English. One flow, but risks breaking its tests
  and clashing with upstream updates.
- C. A terminal question script. Can't read CVs or follow up on vague answers.

The owner picked A.

## Design

### Branch and privacy
- New branch `share` in a separate git worktree, started from `HEAD`
  (= upstream template state for all profile files).
- Brought over from the owner's working copy: `dashboard/` (minus
  `node_modules`, `.next`, `.data`), `Start Job Desk.command`,
  `tools/remote_boards.py`, `tools/ats_boards.py`, `tools/ats_companies.txt`.
- Not brought over: every modified profile file, `job_search_tracker.csv`,
  `cv/`, `cover_letters/` outputs, `company_research/`, `job_scraper/`
  state, `documents/` contents, `.superpowers/`.
- Before pushing: grep the whole branch for the owner's name, phone, email,
  employer names; run the placeholder-integrity check and the test suite.
- Push `share` as `main` of the new private repo. The owner invites the friend.

### Settings file: `my_search.json`
Written by `/start`, gitignored (personal). Plain fields:
```json
{
  "roles": ["product designer", "ux designer"],
  "title_skip": ["intern", "junior"],
  "work_mode": "remote",           // remote | hybrid | onsite | any
  "home": {"city": "Nairobi", "country": "Kenya"},
  "open_to_regions": ["worldwide", "emea", "africa"],
  "skip_regions": [],
  "pay_floor": {"amount": 30000, "currency": "USD", "per": "year"},
  "pay_floor_usd_year": 30000,
  "max_age_days": 30
}
```
- `remote_boards.py` and `ats_boards.py` build their title / region / pay
  filters from this file. No file: exit with a friendly "run /start first".
  Remote-only tools say so and skip cleanly when `work_mode` is `onsite`.
- Dashboard subtitle and the screening-answers prompt read it (and the
  profile) instead of the owner's hardcoded text.

### `/start` command (`.claude/commands/start.md`)
- Tone rules at the top: short sentences, everyday words, one question at a
  time, explain any unavoidable term in brackets the first time, show
  progress ("Step 2 of 5").
- Steps: welcome → jobs wanted → job needs → portfolio links → documents
  (tell them exactly which folder, wait for "done") → hand-off to `/setup`
  with answers → write `my_search.json` and search queries → install check
  for the job-search tools → `/scrape` → `/rank` → "here's your list, here's
  how to apply".
- Safe to re-run; if a profile exists it offers to update one part.
- Checks for missing tools (Python, Bun, LaTeX) and explains how to get them
  in one line each, without blocking the parts that don't need them.

### Auto-trigger
Template `CLAUDE.md` gets a short block at the very top: if the Name still
reads `[YOUR_NAME]`, greet the user and run `/start` before anything else.
`/setup` removes the block when it fills the profile (it replaces the whole
template anyway).

### README
A short "Start here" box at the top of README.md, in the same plain voice:
install Claude Code, clone, open the folder, say hi.

## Left to the builder
- Exact wording of each `/start` question (following the tone rules).
- How `/start` passes answers into `/setup` (inline context is fine).
- Whether `ats_companies.txt` keeps its starter list or becomes a short
  neutral list with a note on how to add companies.

## Calls made during the builder check
- The friend's profile also lands in tracked files. `/start` tells them, in
  one plain line, that their info stays on their computer and not to push
  profile commits to the shared repo (the owner would see it). It offers the
  same private-repo recipe `/setup` already points to.
- `Start Job Desk.command` is Mac-only. Kept, plus a one-line
  `cd dashboard && npm install && npm run build && npm run start` fallback
  in the README for Windows / Linux.
- This doc names no one, because it ships in the shared repo.
