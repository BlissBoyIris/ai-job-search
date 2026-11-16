# Friendly First Run Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A clean, private, shareable copy of this repo where a new user is greeted by a plain-English `/start` flow that collects their job needs, portfolio and CVs, runs `/setup`, then finds and ranks jobs.

**Architecture:** Work on a `share` branch in a separate worktree that starts from the pristine template (`HEAD`). Add a small settings module that turns the user's answers (`my_search.json`) into the filters the board tools used to hardcode. Add a `/start` command spec, an auto-trigger in the blank `CLAUDE.md`, and a README "Start here" box. Push to a new private GitHub repo with `gh`.

**Tech Stack:** Python 3 stdlib + `unittest` (repo convention), Next.js dashboard (existing), Markdown command specs, `gh`.

**Spec:** `docs/superpowers/specs/2026-11-16-friendly-first-run-design.md`

## Global Constraints

- No owner personal data in any committed file on `share`: name, email, phone, employers, clients, city, work authorization. The literal search terms live in an uncommitted scratch file, never in the repo.
- Profile files stay byte-identical to `HEAD` (template placeholders kept; CI placeholder-integrity must pass).
- `my_search.json` is gitignored.
- `/start` copy: short sentences, everyday words, one question at a time, any unavoidable term explained in brackets the first time, progress shown as "Step N of 5".
- Tests run with `python3 -m unittest discover -s tests -t . -v`.
- The owner's local `master` working tree is never modified.

## Review Focus

1. `my_search.json` missing → board tools print "Run /start first" and exit 1, no traceback. (Task 2)
2. User wants on-site only → board tools write `[]`, say why, exit 0. (Task 3)
3. No pay floor given (`pay_floor_usd_year: null`) → no pay filter, nothing crashes. (Task 2)
4. Posting location empty or "Remote" with no region → kept. (Task 2)
5. Hand-edited JSON with a missing optional key → defaults apply instead of `KeyError`. (Task 2)

---

### Task 1: Clean `share` worktree

**Files:**
- Create worktree: `../AIJS-share` on new branch `share` from `HEAD`
- Copy from owner tree: `dashboard/` (exclude `node_modules`, `.next`, `.data`, `tsconfig.tsbuildinfo`), `Start Job Desk.command`, `tools/remote_boards.py`, `tools/ats_boards.py`, `tools/ats_companies.txt`, the spec and this plan
- Modify: `.gitignore` (add `my_search.json`, `dashboard/.data/`, `dashboard/.next/`, `dashboard/tsconfig.tsbuildinfo`)

- [ ] **Step 1:** `git worktree add ../AIJS-share -b share HEAD`; `rsync` the files above.
- [ ] **Step 2:** Run the suite in the worktree. Expected: same pass/skip set as `HEAD` (baseline).
- [ ] **Step 3:** Commit `chore: bring over dashboard and board tools`.

### Task 2: `tools/search_settings.py`

**Files:** Create `tools/search_settings.py`; Test `tests/test_search_settings.py`

**Interfaces — Produces:**
- `DEFAULT_PATH: Path` = repo root / `my_search.json`
- `class SettingsMissing(Exception)` — message contains "Run /start first"
- `@dataclass Settings`: `roles: list[str]`, `title_skip: list[str]`, `work_mode: str` (`remote|hybrid|onsite|any`, default `remote`), `home_city: str`, `home_country: str`, `open_to_regions: list[str]` (always includes `worldwide`, `anywhere`, `global`), `skip_regions: list[str]`, `pay_floor_usd_year: float | None`, `max_age_days: int` (default 30)
- `load(path: Path | None = None) -> Settings`
- `Settings.title_yes() -> re.Pattern`, `Settings.title_no() -> re.Pattern` (escaped words, `re.I`; `title_no` always includes `intern`, `internship`)
- `Settings.region_ok(text: str, restrictions: list[str] | None = None) -> tuple[bool, str]` — same rules as today's `remote_boards.region_ok`, with the owner's home → `home_country`/`home_city`, wide-region list → `open_to_regions`, low-pay list → `skip_regions`

- [ ] **Step 1: Failing tests** (`unittest`, temp-dir JSON files):
  - `test_missing_file_raises_friendly` → `SettingsMissing`, `"Run /start first" in str(e)`
  - `test_defaults_fill_missing_keys` → file `{"roles":["designer"]}` gives `work_mode == "remote"`, `max_age_days == 30`, `pay_floor_usd_year is None`
  - `test_title_patterns` → roles `["product designer"]`, `title_skip ["junior"]`: yes matches "Senior Product Designer", no matches "Junior Product Designer"
  - `test_region_empty_or_unstated_ok` → `region_ok("")[0]` and `region_ok("", [])[0]` are True
  - `test_region_home_country_allowed` → home "Kenya": `region_ok("", ["Kenya","Nigeria"])[0]` True; `region_ok("", ["United States"])[0]` False
  - `test_region_skip_unless_wide` → skip `["brazil"]`: "Brazil" False, "Brazil, Worldwide" True
- [ ] **Step 2:** Run; expect ImportError failures.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run; expect PASS.
- [ ] **Step 5:** Commit `feat(tools): search settings from my_search.json`.

### Task 3: Rewire board tools

**Files:** Modify `tools/remote_boards.py` (constants block, `region_ok`, `keep`, `main`), `tools/ats_boards.py` (imports, `remote_region_ok`, `main`); Test `tests/test_board_tools.py`

**Interfaces — Consumes:** Task 2. **Produces:** `remote_boards.keep(job, cutoff, why, s: Settings) -> bool`; both CLIs gain `--settings PATH`; `--days` defaults to `s.max_age_days`.

- [ ] **Step 1: Failing tests:**
  - `test_keep_uses_settings_roles` → `keep` on `{"title":"Product Designer", ...}` True with designer settings, False with settings for a different role
  - `test_keep_pay_floor_optional` → `_annual=20000`: dropped when floor 30000, kept when floor None
  - `test_cli_missing_settings_exit_1` → subprocess `remote_boards.py --out x --settings /nonexistent` exits 1, stderr has "Run /start first", no "Traceback"
  - `test_cli_onsite_writes_empty` → onsite settings: both CLIs exit 0, out file is `[]`, stdout mentions "on-site" (no network hit: return before fetching)
  - `test_no_hardcoded_filters` → neither source defines the old hardcoded title / region / pay constants
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement. Module docstrings describe generic behaviour. `ats_boards` keeps `REMOTE`; its wide/narrow check calls `s.region_ok`.
- [ ] **Step 4:** Run; expect PASS. Smoke: `python3 tools/remote_boards.py --out /tmp/x.json --settings <sample> --explain` returns JSON summary.
- [ ] **Step 5:** Add `ats_companies.txt` header comment: what it is, how to add a company. Commit `refactor(tools): board tools read my_search.json`.

### Task 4: Dashboard reads the user, not the owner

**Files:** Modify `dashboard/lib/runner.ts` (`runAnswers` prompt), `dashboard/app/page.tsx:133`, `dashboard/lib/repo.ts` (add `readSearchSettings()`), `dashboard/app/api/jobs/route.ts` (include `subtitle`), `dashboard/README.md`, `Start Job Desk.command`

- [ ] **Step 1:** `runAnswers`: replace the salary / work-authorization / notice lines with "take salary, work authorization, notice period and time zones from CLAUDE.md's Candidate Profile; if missing, say so in the answer". Replace "he" with "the candidate".
- [ ] **Step 2:** Subtitle built from `my_search.json`: `"<Work mode> <roles joined with ', '> roles"` plus `", <currency> <amount> per <per> and up"` when a floor exists; fallback "Run /start to set up your search."
- [ ] **Step 3:** `Start Job Desk.command`: drop machine-specific PATH entries except Homebrew and TeX; if `npm` missing, print a one-line install hint and exit.
- [ ] **Step 4:** `cd dashboard && npm install && npm run build`. Expected: build succeeds. grep the dashboard for the owner's terms (list kept outside the repo) → no hits.
- [ ] **Step 5:** Commit `feat(dashboard): use the user's own search settings`.

### Task 5: `/start`, auto-trigger, README

**Files:** Create `.claude/commands/start.md`; Modify `CLAUDE.md` (top block only), `.claude/skills/job-scraper/search-queries.md` (add "Extra remote boards" section), `README.md` (Start-here box after the title); Test `tests/test_start_command.py`

**`start.md` structure** (frontmatter `description:`; title `# /start - Friendly First Run`):
1. Tone rules (Global Constraints copy rules, plus: never paste file paths without saying what they are; no tables).
2. Step 0: if CLAUDE.md has no `[YOUR_NAME]`, offer "update one part" instead (roles / needs / links / documents / search) and jump there.
3. Step 1 of 5 Jobs: kind of work in their words → suggest 3-8 titles → confirm.
4. Step 2 of 5 Needs, one at a time: work mode; city + country; countries they can legally work in; lowest pay with currency and per month/year (convert to USD/year for `pay_floor_usd_year`, say the converted figure back); deal-breakers; how recent postings should be (default 30 days).
5. Step 3 of 5 Links: portfolio, LinkedIn, GitHub, site — any "skip".
6. Step 4 of 5 Documents: tell them to drop files into `documents/cv/`, `documents/linkedin/`, `documents/projects/`; wait for "done"; or paste a CV; or "I have none".
7. Hand-off: follow `.claude/commands/setup.md` Path A/B/C (by what Step 4 got), skipping Step 0's path prompt and every question already answered; Section 9 gets the Step 1-2 answers. Privacy line: "Your info stays on this computer. Don't push it to the shared repo — the owner would see it."
8. Write `my_search.json`; ensure search-queries.md has the "Extra remote boards" section (re-add if `/setup` regenerated it).
9. Step 5 of 5 Find jobs: check `python3`, `bun` (portal CLIs; `python3 tools/install_portal_clis.py`), LaTeX (only needed for `/apply`) — one-line fix each, non-blocking. Run `/scrape`, then `/rank`. Show the top 10 in a short list. Close with: "Pick one and type `/apply` plus its link."

- [ ] **Step 1: Failing tests:**
  - `test_start_command_exists_with_frontmatter` → file exists, frontmatter has `description`, first heading starts `# /start`
  - `test_start_covers_every_question` → contains each of: `work mode`/`remote`, `legally work`, `lowest pay`, `deal-breaker`, `portfolio`, `documents/cv/`, `my_search.json`, `/scrape`, `/rank`, `setup.md`
  - `test_start_shows_progress` → `Step 1 of 5` … `Step 5 of 5` all present
  - `test_claude_md_auto_trigger` → CLAUDE.md first 15 lines mention `[YOUR_NAME]` and `/start`
  - `test_search_queries_mentions_board_tools` → template contains `tools/remote_boards.py` and `my_search.json`
  - `test_readme_start_here` → README first 40 lines contain "Start here" and "/start"
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Write the four files. README box ≤ 12 lines; includes the dashboard fallback `cd dashboard && npm install && npm run build && npm run start`.
- [ ] **Step 4:** Run the new tests + `python3 tools/lint_skills.py`; expect PASS. Read `start.md` aloud-test: no sentence over ~20 words in user-facing copy.
- [ ] **Step 5:** Commit `feat: /start friendly first run`.

### Task 6: Privacy sweep, full suite, push

- [ ] **Step 1:** `git grep -niE -f <scratch terms file> share` (terms file outside the repo) → zero hits. Also check `git log share` adds no author email beyond git's own commit metadata.
- [ ] **Step 2:** Full suite → no new failures vs Task 1 baseline.
- [ ] **Step 3:** `gh repo create <name> --private --source ../AIJS-share --remote origin`; `git push -u origin share:main`.
- [ ] **Step 4:** `gh repo view --json visibility` → `PRIVATE`. Tell the owner how to invite the friend (`gh repo add-collaborator` / Settings → Collaborators).
