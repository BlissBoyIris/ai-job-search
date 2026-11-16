# Job Desk

A local dashboard for this repo's `/scrape`, `/rank` and `/apply` workflows.

Open it by double-clicking `Start Job Desk.command` in the repo root (Mac). On Linux, run `npm install && npm run build && npm run start` in this folder and go to http://127.0.0.1:3300. It only listens on your own machine. Windows is not supported yet (the run launcher assumes a Unix shell and `python3`). Run `/start` in Claude Code first, so the dashboard knows what you are looking for.

- **Scrape** and **Rank** run the repo's own commands through Claude Code in the background. The table refreshes every few seconds from `job_scraper/seen_jobs.json`.
- **Write CV and cover letter** runs the full `/apply` workflow for one job (fit check, tailored LaTeX CV and cover letter, reviewer pass, PDF compile, tracker row). It takes about 5-10 minutes. **Write CVs for top N** queues several, two at a time.
- **Get answers** drafts screening-question answers grounded in your profile, with copy buttons.
- **Remove weak fits (N)** sits next to the job count in the Open list. It skips every ranked Weak Fit / Poor Fit job and every unranked job the scrape rated low, except jobs that already have a CV. Skipped jobs never come back on a scrape. Select rows and press **Delete** to remove specific ones instead.
- **Mark as applied** updates `job_search_tracker.csv`, so the job never comes back and the counter goes up.

Claude Code comes from the VS Code extension (set `CLAUDE_BIN` to use another copy). Runs use your Claude account. Run logs are in `.data/runs/` and dashboard results in `.data/apps.json`.

After changing code here, run `npm run build` again before `npm run start`.
