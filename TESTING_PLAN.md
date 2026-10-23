# End-to-End Testing Plan (job-seeker walkthrough)

This plan walks through job-agent the way a real job-seeker would use it, starting from a fresh clone. It uses **no sample data**: you use your own CV, your own preferences and real, live job postings.

The plan is written for a tester called **Riddhi**, a job-seeker in the US and/or Canada who is not applying yet. Replace "Riddhi" with yourself. Everything you do here stays on your machine unless you push it.

**Out of scope:** `/apply` (drafting and tailoring CVs and cover letters for a specific job). Nothing in this plan submits an application or contacts an employer.

## How to use this plan

- Work through the stages in order. Each stage lists **Do**, **Expect** and a **Result** line for you to mark.
- Mark each check `[x]` on pass. On failure, write the symptom in the **Defect log** at the end (stage, what you typed, what you saw, what you expected) and keep going unless the stage says it blocks the next ones.
- Judgement checks ("is this score sensible?") matter as much as mechanical ones. The tool is only useful if you would trust its answers.
- Time needed: about 2 to 3 hours for stages 0 to 10; the optional stages (11 to 13) depend on which accounts you have.

## Privacy rules while testing

- `/setup` writes your name, phone, email and employment history into **tracked** files (`CLAUDE.md` and files in `.claude/skills/job-application-assistant/`). **Do not commit or push these.** If you keep the repo private and local, you are fine.
- Before any `git commit`, run `git status` and read the list. Never use `git add -A` after `/setup`.
- Your CV, `job_scraper/`, `job_search_tracker.csv`, `documents/**` contents and `.env` are gitignored. Confirm that in stage 14.
- Use a throwaway clone if you want to be completely sure nothing leaks.

---

## Stage 0: Prerequisites

**Do**

1. Install an AI coding agent. Claude Code gives the full experience; Gemini CLI, Cursor, Codex and Copilot also work through `AGENTS.md`.
2. Check Python 3.10 or newer: `python3 --version` (Windows: `py --version`).
3. Install Bun: `curl -fsSL https://bun.sh/install | bash` (Windows PowerShell: `irm https://bun.sh/install.ps1 | iex`). Open a new terminal, then run `bun --version`.
4. Install a LaTeX distribution only if you want to compile documents later (MacTeX or BasicTeX on macOS, MiKTeX on Windows, TeX Live on Linux). Not needed for this plan, which skips `/apply`.

**Expect**

- [ ] `python3 --version` prints 3.10+.
- [ ] `bun --version` prints a version in a new terminal. If not, add `~/.bun/bin` to your PATH.
- [ ] The agent starts (`claude --version`, or the equivalent for your agent).

Result: ____

---

## Stage 1: Fresh clone and automated health check

**Do**

```bash
git clone https://github.com/harshal1900/job-agent.git
cd job-agent
git status
python3 -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install pytest pypdf
python3 tools/install_portal_clis.py
python3 -m pytest -q
python3 tools/security_guards.py
python3 tools/sync_agent_wrappers.py --check
python3 tools/token_budget.py
for d in ats-search linkedin-search freehire-search; do (cd .agents/skills/$d/cli && bun test); done
```

**Expect**

- [ ] `git status` says the working tree is clean.
- [ ] `install_portal_clis.py` finishes without errors for all three CLIs.
- [ ] `pytest` shows all tests passing (a few skips for missing optional tools are fine).
- [ ] `security_guards.py` and `sync_agent_wrappers.py --check` print OK.
- [ ] `token_budget.py` prints a table with no budget exceeded.
- [ ] Each `bun test` run ends with 0 failures.

Result: ____

---

## Stage 2: Pre-setup state (nothing personal exists yet)

**Do**

1. Open `CLAUDE.md` and `.claude/skills/job-application-assistant/01-candidate-profile.md`.
2. Open `config/target_companies.json`.
3. List `documents/` and its subfolders.

**Expect**

- [ ] Both profile files still contain placeholders such as `[YOUR_NAME]`.
- [ ] `target_companies.json` lists about 30 companies across Greenhouse, Lever, Ashby and Workday.
- [ ] `documents/` subfolders are empty (only README files).
- [ ] No name, email or phone of any real person appears anywhere in the repository. Spot-check with `grep -ri "@gmail.com" --include=*.md --include=*.json . | head`.

Result: ____

---

## Stage 3: Onboarding with `/setup`

Prepare your own CV as **both** a `.docx` and a `.pdf` (the same CV in two formats). Copy both into `documents/cv/`. Optionally add your LinkedIn data export to `documents/linkedin/`, plus diplomas, reference letters and project write-ups in their folders. See `documents/README.md`.

### 3a. Input extraction check (before launching the agent)

```bash
python3 tools/extract_cv_text.py "documents/cv/<your-cv>.docx"
python3 tools/extract_cv_text.py "documents/cv/<your-cv>.pdf"
```

- [ ] Both print a JSON status line, then your CV text.
- [ ] Name, contact line, job titles, dates, education and skills all appear in both outputs.
- [ ] Header and footer content (often contact details) appears for the `.docx`.
- [ ] If the `.docx` contains hidden text, the status line reports `hidden_runs_dropped` above 0.
- [ ] The two texts agree on facts. Small bullet-glyph and hyphenation differences are expected.

### 3b. Run the onboarding

Start the agent in the repository and run `/setup`.

- [ ] It scans `documents/` and lists what it found per folder.
- [ ] It offers Path A (documents folder), Path B (single CV) and Path C (interview). Choose **Path A**.
- [ ] If your `origin` remote were a public fork, it would warn before writing anything. For a private or local clone it continues silently.
- [ ] It reads the `.docx` through the extractor and the `.pdf` directly.
- [ ] **Cross-reference check:** if your two CVs disagree on a date or title, it lists each conflict and waits for your decision. If they agree, it says so.
- [ ] It proposes changes grouped by file and **waits for your confirmation** before writing anything.
- [ ] It asks about the gaps a CV does not cover:
  - [ ] work authorization and sponsorship needs (US and/or Canada)
  - [ ] location (city, state or province), remote/hybrid/onsite, relocation
  - [ ] languages and levels
  - [ ] target roles, what excites you, deal-breakers
  - [ ] salary expectations (optional)
  - [ ] which companies to watch
- [ ] Answer honestly. Note any question you found confusing in the defect log.

### 3c. Verify what it wrote

- [ ] `CLAUDE.md` has no `[YOUR_...]` placeholders left in Identity, Education, Experience and Skills.
- [ ] Work authorization is recorded exactly as you stated it.
- [ ] Every fact in `01-candidate-profile.md` (titles, employers, dates, degrees, skills) matches your CV. Search for invented content: anything you did not say is a defect.
- [ ] `02-behavioral-profile.md` additions are labelled as inferred, or left as placeholders if you had no source.
- [ ] `cv/main_example.tex` has your name and contact details. Letter paper is used (`letterpaper`), and there is no References section.
- [ ] `05-cv-templates.md` and `06-cover-letter-templates.md` have your contact block and signature, with no placeholders.
- [ ] `.claude/skills/job-scraper/search-queries.md` has your roles, skills, location tiers and company list, with no placeholders.
- [ ] `07-interview-prep.md` contains STAR stubs for you to fill, not invented stories.
- [ ] The final summary lists the generated files and reminds you not to push personal data to a public repo.

Result: ____

### 3d. Alternative paths (repeat in a scratch clone if you want coverage)

- [ ] **Path B:** reset (stage 13), then use `@documents/cv/<file>` with Path B. It extracts and asks follow-up questions.
- [ ] **Path C:** reset again, then answer the interview questions. It should feel like a conversation and let you skip optional sections.
- [ ] **`/setup --section search`:** jumps straight to search configuration without redoing the whole profile.
- [ ] **Re-run `/setup` Path A** with no new documents. It should propose nothing new (idempotent) and not duplicate content.

---

## Stage 4: `/expand` (optional enrichment)

**Do**: run `/expand`. Give it a project folder, your GitHub profile or LinkedIn export if you have them.

- [ ] It reads the existing profile first and does not propose duplicates.
- [ ] Each proposed competency is shown for your approval, with its source.
- [ ] Nothing existing is modified, and nothing is added without your yes.
- [ ] Anything you reject does not appear in the profile files.

Result: ____

---

## Stage 5: Company watchlist and the ATS search tool (no agent needed)

Set an alias to save typing: `alias ats="bun run .agents/skills/ats-search/cli/src/cli.ts"`.

### 5a. Watchlist health

```bash
ats companies --check
```

- [ ] Every board in `config/target_companies.json` resolves with a job count. Failures are reported per board, not as a crash.

### 5b. Add companies you care about

For each employer you would really like to work for, find its careers URL, identify the system and token (see "Finding a company's token" in `.agents/skills/ats-search/SKILL.md`), and add it to `config/target_companies.json`.

- [ ] `ats companies --check` confirms each new board.
- [ ] A company whose careers site is on another system (or none of the four) is noted; use `/add-portal` for that (stage 12).

### 5c. Searches

Use your own role keywords and location.

```bash
ats search -q "<your title>" --format table
ats search -q "<title 1> OR <title 2>" --country us,ca --jobage 14 --format table
ats search -q "<your title>" --remote remote --format table
ats search -q "<your title>" --location "<your metro>" --format table
ats search -q "<your title>" --country ca --format table
ats search -q "<your title>" --company <one watched company> --format json | head -c 1500
ats search -q "<your title>" --limit 5 --page 2 --format table
```

- [ ] Results are real, recent postings with company, title, location and a link.
- [ ] `--country us` and `--country ca` return only that country. Open three results by hand and confirm the location.
- [ ] `--remote remote` returns remote roles; `--location` narrows to the metro.
- [ ] `--jobage 14` returns nothing older than 14 days (check posted dates).
- [ ] The JSON output includes a `meta` block with counts of what was dropped.
- [ ] Open at least five postings in a browser. Each link works and is the same job the tool reported.
- [ ] Salary ranges, where shown, match the posting.
- [ ] A nonsense query (for example `-q zzzqqq --company stripe --format table`) prints "(no matching jobs)" with no stack trace.
- [ ] `ats search --board greenhouse:thiscompanydoesnotexist -q x --format plain` prints a `BOARD_FAILED` warning ("board not found") for that board and still returns results from your other boards.

### 5d. Detail view

```bash
ats detail <url from a search result>
```

- [ ] Prints the full posting text with no HTML noise or doubled escapes.

Result: ____

---

## Stage 6: `/scrape`

**Do**: run `/scrape`.

- [ ] It discovers the installed portals (`ats-search`, `linkedin-search`, `freehire-search`) and runs them with queries derived from your profile and `search-queries.md`.
- [ ] Results are limited to the United States and Canada, and respect your location tiers.
- [ ] It shows a summary of new jobs, with title, company, location, source and link, rather than dumping raw files.
- [ ] A posting that requires a clearance or US citizenship, or one that rules out your work authorization, is excluded or flagged.
- [ ] A posting requiring a language you did not declare is excluded.
- [ ] Run `/scrape` a **second time** right away: it reports no repeated jobs (deduplication).
- [ ] If one portal fails (for example LinkedIn blocks you), `/scrape` says so and continues with the others.
- [ ] `job_scraper/seen_jobs.json` exists and `git status` does **not** list it (it is ignored).
- [ ] It offers a sensible next step (`/rank`).

Result: ____

---

## Stage 7: `/rank`

**Do**: run `/rank`, then `/rank --limit 5 --top 3`, then `/rank <a focus word from your field>`.

- [ ] It scores postings against your profile and returns a shortlist with a score and reasons per job.
- [ ] It says clearly that these are triage scores, not final evaluations.
- [ ] **Judge the scores.** Take the top, a middle and the bottom job and read the postings yourself. Do you agree with the order? Record disagreements in the defect log.
- [ ] A job needing sponsorship you cannot get, a clearance, or a language you lack is not ranked highly.
- [ ] A posting that fails the integrity gate (closed, expired or suspicious) is flagged, not silently scored.
- [ ] `--limit` and `--top` change how many are scored and shown, and deferred jobs are not lost.
- [ ] `/rank --all` re-ranks, including jobs ranked before.
- [ ] Ranked jobs are not offered again by a plain `/rank`.

Result: ____

---

## Stage 8: Single-job fit evaluation (the assistant skill, without drafting)

Pick two real postings from your shortlist, one strong match and one you suspect is a poor match. Paste the URL, then do the same with the text pasted in.

Ask: "Evaluate my fit for this role." **Do not** proceed to drafting documents. Stop after the assessment.

- [ ] The agent fetches the posting, runs the integrity check, and shows its verdict.
- [ ] You get a structured assessment: skills match, experience match, behavioral/culture fit, eligibility (work authorization, language, location, salary), with a clear recommendation.
- [ ] Claims about you match your profile. It does not invent experience.
- [ ] It **asks before** doing any CV or cover letter work.
- [ ] The poor-match posting is told honestly as a poor match.
- [ ] A dead or invalid URL gives a clean error, not made-up content.
- [ ] Pasted text produces the same quality as a URL.
- [ ] Salary comparison appears only if you configured salary data (stage 14b). Otherwise it is skipped without error.

Result: ____

---

## Stage 9: Registering a real application and tracking (without applying)

You are not applying, so use the tracker for a job you are *considering*. `/outcome` can register an application made outside the workflow.

**Do**: run `/outcome <company>` for one real posting you are considering. Provide the company, role, date, channel and URL when asked, and set the status to `drafted`.

- [ ] `job_search_tracker.csv` is created with the standard header (ending in `deadline`).
- [ ] The row has the details you gave.
- [ ] `documents/applications/<company>_<role>/outcome.md` is created.
- [ ] `drafted` is listed under "Drafted, not yet submitted" and not counted as quiet.
- [ ] Run `/scrape` again: that company and role no longer appear as new.
- [ ] Run `/outcome` with no argument: it lists open applications.
- [ ] `git status` does not list the tracker as a trackable file.

Result: ____

---

## Stage 10: `/upskill` and `/interview`

### `/upskill`

**Do**: run `/upskill` (aggregate mode), then `/upskill <posting URL>` (targeted).

- [ ] Aggregate mode uses the tracker and your ranked jobs.
- [ ] You get a skill-gap heatmap and a prioritized learning plan with real, working study links.
- [ ] The gaps are real ones. Skills you already have are not listed as missing.
- [ ] Targeted mode analyses just the one posting.

### `/interview`

`/interview` is built for a real, scheduled interview. To rehearse the flow without one, treat it as a dry run and delete the test row afterwards.

**Do**: run `/interview <company>` on the row from stage 9.

- [ ] It loads the application context and asks for the interview stage, date, format and interviewers.
- [ ] It researches the company with cited sources.
- [ ] It builds talking points, STAR answers and questions to ask, consistent with your profile.
- [ ] It does not claim experience you do not have.
- [ ] Afterwards, remove the dry-run row if you do not want it. Keep the file consistent: remove the row and the `documents/applications/...` folder together.

Result: ____

---

## Stage 11: Outcome and follow-up handling

Use a throwaway row so you do not pollute real data.

**Do**: register a test row via `/outcome`, then try the following.

- [ ] `/outcome <company>` and record a progress update (for example "interview scheduled"). The status changes in the CSV.
- [ ] Record a final result "rejected". The status becomes final, with no donation or promotional prompt.
- [ ] `/outcome followup` lists applications quiet for 10 days or more (you can test with an older date) and drafts a short follow-up note. It does **not** send anything.
- [ ] `/outcome stale` handles applications quiet for 60+ days.
- [ ] Remove the test row and its folder when done.

Result: ____

---

## Stage 12: Dashboard and portals

### `/html-report`

- [ ] `/html-report` writes `reports/application-dashboard.html`.
- [ ] Open it in a browser. It shows your tracked jobs with sensible statuses and dates. It is a single file with no external dependencies.
- [ ] `reports/` is not tracked by git.

### `/add-portal` (optional)

Only if you use a job board that has no search tool, such as Indeed, Dice, Wellfound or Job Bank Canada.

- [ ] It asks about the portal, builds a search skill and test-runs a real query before registering it.
- [ ] `/scrape` then picks up the new portal. If the test run fails, the portal is not left half-installed.

### `/add-template` (optional)

Only if you have your own LaTeX CV or cover letter template.

- [ ] It captures the compile engine, fonts, page limit and style, and test-compiles (needs LaTeX).

Result: ____

---

## Stage 13: Integrations (only those you use)

- [ ] **`/gmail-sync`:** needs your own Gmail connector. It reads application emails and proposes status changes. Nothing is changed or sent without your confirmation.
- [ ] **`/notion-sync`:** needs your own Notion connector. It pushes ranked jobs and applications to a database. You approve what is written.
- [ ] Without the connector, the command says what is missing and stops. It does not fail with a stack trace.

Result: ____

---

## Stage 14: Resilience, privacy and cleanup

### 14a. Reset and re-run

- [ ] `/reset` asks for scope and an explicit confirmation before deleting anything.
- [ ] After a full reset, the profile files go back to placeholders.
- [ ] Running `/setup` again works from scratch.

### 14b. Optional salary data

Only if you have salary data. See `SETUP.md` section 5 (`salary_data.json` or the Excel converter).

- [ ] With the file present, fit evaluations include a salary benchmark.
- [ ] Without it, the benchmark is skipped without error.

### 14c. Other agents (optional)

- [ ] **Gemini CLI:** the `/scrape`, `/rank` and other commands exist and follow the same steps.
- [ ] **Cursor, Codex or Copilot:** ask "find me jobs" with `AGENTS.md` as the entry. It runs the same search commands and respects the same rules.
- [ ] Where the agent has no subagents, `AGENTS.md` tells it how to do the reviewer and scorer steps inline.

### 14d. Privacy check (always do this last)

```bash
git status --short
git check-ignore -v job_scraper/seen_jobs.json job_search_tracker.csv documents/cv/<your-cv>.pdf reports/x.html
```

- [ ] `git status` lists only the profile files `/setup` is expected to change (`CLAUDE.md`, `.claude/skills/job-application-assistant/*`, `cv/main_example.tex`, `.claude/skills/job-scraper/search-queries.md`, `config/target_companies.json`).
- [ ] `job_scraper/`, the tracker CSV, your CV files and `reports/` are all ignored.
- [ ] No `.env` or other secrets are listed.
- [ ] You decide what to do with the personal changes: keep them local (best), or `git checkout -- .` to discard them.

---

## Pass criteria

The tool passes if all of the following hold:

1. Stages 1, 3, 5, 6, 7 and 8 pass, with no invented facts about you anywhere.
2. Searches return real, US/Canada, reasonably fresh postings that match what you asked for.
3. The ranking agrees with your own judgement on most of the jobs you checked by hand.
4. No personal data would be committed by accident (stage 14d).
5. You would trust the shortlist and the fit assessment enough to start applying.

## Defect log

Copy one row per issue.

| # | Stage | What I did (exact command or message) | What happened | What I expected | Severity (blocker / wrong result / annoyance) |
|---|-------|---------------------------------------|---------------|-----------------|-----------------------------------------------|
| 1 |       |                                       |               |                 |                                               |

## Known limits to keep in mind

- `/apply` is not covered here.
- Gemini CLI, Cursor and Codex support was written from the official documentation. It has not been exercised in those agents, so report any difference.
- `ats-search` only searches the companies in `config/target_companies.json`. It is not a whole-market search.
- Keywords match the job title and department, not the full description.
- A posting whose location is just "Remote" (no country) is dropped unless you pass `--include-unspecified-location`.
- Workday does not date every posting, so `--jobage` drops those.
