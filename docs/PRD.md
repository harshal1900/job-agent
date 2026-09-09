# Autonomous AI Job Search & Application Agent — PRD & Architecture

**Owner:** Harshal Patel
**Target environment:** 2018 Intel MacBook Pro, 16GB RAM, local-only, $0 infra cost
**Orchestration model:** Claude Web/Desktop Chat (planning) → Claude Cowork (file/data ops) → Claude Code / VS Code extension (build + run)

---

## 1. Product Requirement Document

### 1.1 Problem
Manually finding, tailoring, and applying to jobs across multiple ATS platforms (Greenhouse, Lever, Workday) is slow and repetitive. The goal is a local, zero-cost agent that discovers matching jobs, tailors application materials, gets human approval by email, and submits the application automatically.

### 1.2 Non-negotiable constraints
- **Zero ongoing infra cost** — every component must have a permanent free tier or run fully local.
- **Human-in-the-loop** — no application is submitted without an explicit APPROVE click.
- **No hallucinated résumé content** — tailoring may only reorder/reword facts already in `master_profile.json`, never invent them.
- **Runs on modest hardware** — no local LLM inference; use hosted free-tier inference (OpenRouter / HF) instead of running models on-device.

### 1.3 Tech stack (as specified)
| Layer | Choice | Notes |
|---|---|---|
| Backend | Python 3.11+, FastAPI | REST + webhook endpoints |
| Scheduler | APScheduler | in-process cron for scans/checks |
| DB | Supabase (Postgres) free tier + SQLite fallback | SQLite is the dev/offline default |
| LLM | OpenRouter free models / HF Inference API | swappable via config |
| Scraping/automation | Playwright (Python, headless Chromium) | job discovery + ATS form fill |
| Webhook exposure | Ngrok free tier | only active during approval windows |
| Notifications | Gmail SMTP (App Password) or Resend free tier | HTML emails with action links |

### 1.4 Key risks to flag (design honestly, don't paper over)
- **ATS Terms of Service**: Greenhouse/Lever/Workday generally prohibit automated scraping and automated form submission in their ToS. Auto-submitting applications via Playwright can get accounts/IPs flagged or blocked, and in some cases violates the site's terms. This doesn't mean the project can't be built — but the PRD should treat auto-submission as a **feature flag**, defaulting to "prepare + open browser for you to click submit" rather than fully autonomous submission, with full autonomy as an opt-in the user explicitly enables per-site.
- **Ngrok free tier** exposes a public URL — the `/approve` and `/reject` endpoints must be protected (signed, single-use, expiring tokens), not just an `id` in a query string, or anyone with the link can approve/reject on your behalf.
- **Email-based approval links** are commonly pre-fetched by corporate email security scanners (Gmail/Outlook link-scanning), which can silently trigger GET requests and auto-"click" your approve link. Use POST-based confirmation pages, not bare GET webhooks, for anything state-changing.
- **Job-closing detector** hitting the same URLs every 24h at scale can look like scraping abuse — keep request volume low and respect `robots.txt`/rate limits per site.

### 1.5 Success criteria
- Agent runs unattended via APScheduler and surfaces new matches within one scan cycle.
- Every match includes a match score, keyword gap list, and tailored resume/cover letter draft grounded only in `master_profile.json`.
- Approval workflow requires a signed, expiring link and confirms via POST before any Playwright action fires.
- Closed/expired postings are detected and reflected in DB + email within 24h.

---

## 2. System Architecture Overview

```
┌─────────────────┐      ┌──────────────────┐      ┌───────────────────┐
│  Job Discovery   │─────▶│  Match & Rewrite  │─────▶│  Approval Email    │
│  (Playwright +   │      │  Engine (LLM via  │      │  (SMTP/Resend +    │
│   APScheduler)   │      │  OpenRouter/HF)   │      │   signed webhook)  │
└─────────────────┘      └──────────────────┘      └─────────┬──────────┘
                                                                │ click
                                                                ▼
┌─────────────────┐      ┌──────────────────┐      ┌───────────────────┐
│  Status Tracker  │◀─────│  Playwright ATS   │◀─────│  FastAPI Webhook   │
│  (24h job-close  │      │  Auto-Fill Engine │      │  (/approve,/reject)│
│   checker)       │      │                    │      │                    │
└─────────────────┘      └──────────────────┘      └───────────────────┘
              │
              ▼
        SQLite / Supabase (job records, statuses, history)
```

**Data flow:** scheduler triggers scrape → new postings diffed against DB → LLM scores + tailors materials → row saved as `PENDING_APPROVAL` → email sent → user clicks signed link → FastAPI confirms via POST landing page → Playwright fills and submits (or opens browser for manual submit, per flag) → status updated → 24h checker maintains lifecycle.

---

## 3. Repository File Tree

```
job-agent/
├── .env.example
├── requirements.txt
├── README.md
├── config/
│   ├── settings.py            # env loading, feature flags (AUTO_SUBMIT=false default)
│   ├── master_profile.json    # personal info, experience, salary floor, visa needs
│   └── target_boards.yaml     # list of company career board URLs to scan
├── database/
│   ├── models.py              # SQLAlchemy models (Job, Application, ApprovalToken)
│   ├── db.py                  # SQLite/Supabase connection switch
│   └── migrations/
├── scrapers/
│   ├── base_scraper.py
│   ├── greenhouse_scraper.py
│   ├── lever_scraper.py
│   └── workday_scraper.py
├── llm/
│   ├── client.py               # OpenRouter/HF wrapper, model swap via config
│   ├── match_scorer.py         # JD vs profile scoring
│   ├── resume_rewriter.py      # anti-hallucination guarded rewriting
│   └── prep_generator.py       # STAR Q&A + tutorial links
├── automation/
│   ├── playwright_runner.py
│   ├── ats_forms/
│   │   ├── greenhouse_form.py
│   │   ├── lever_form.py
│   │   └── workday_form.py
│   └── status_checker.py       # 24h link/status check job
├── api/
│   ├── main.py                 # FastAPI app entrypoint
│   ├── routes_approval.py      # /approve, /reject, /mark-status
│   ├── security.py             # signed/expiring token verification
│   └── scheduler.py            # APScheduler job registration
├── templates/
│   ├── email_match.html
│   ├── email_prep_package.html
│   └── approval_landing.html
└── tests/
    └── ...
```

---

## 4. Handoff Prompt — Claude Code / VS Code Extension

Copy everything between the lines into Claude Code once you're ready to build:

```
I'm building "Autonomous AI Job Search & Application Agent" locally on a 2018 Intel
MacBook Pro (16GB RAM), zero paid infra. Stack: Python 3.11 + FastAPI + APScheduler,
SQLite (Supabase-compatible schema for later), OpenRouter free-tier LLM, Playwright
(Python) for scraping + ATS form-fill, Ngrok free tier for webhook exposure, Gmail
SMTP for email.

Please scaffold the repo using this file tree: [paste Section 3 tree above].

Build order:
1. requirements.txt + config/settings.py with feature flags, especially
   AUTO_SUBMIT_APPLICATIONS (default false — draft-and-open-browser mode until I
   explicitly opt in per ATS).
2. database/models.py + db.py — SQLite first, structured so swapping to Supabase
   later only touches db.py.
3. scrapers/ — start with greenhouse_scraper.py only; get one working end-to-end
   before adding lever/workday.
4. llm/client.py against OpenRouter's free-tier chat completions endpoint; keep the
   model name in config so I can swap it.
5. llm/resume_rewriter.py — hard-enforce that it can only use facts present in
   config/master_profile.json; add a validation step that flags any noun phrase in
   the output not traceable to the profile JSON.
6. api/security.py — signed, single-use, time-expiring tokens for approval links
   (not raw job IDs in a GET query string). Approval must be a POST from a landing
   page, not a bare GET, to survive email link-scanners safely.
7. api/routes_approval.py + automation/playwright_runner.py, gated behind
   AUTO_SUBMIT_APPLICATIONS.
8. automation/status_checker.py as an APScheduler job running every 24h.
9. Set up Playwright (`playwright install chromium`), run one full local end-to-end
   cycle against a single test posting, and show me the terminal output.

Install and run everything locally — no cloud deploy. Ask me before enabling
AUTO_SUBMIT_APPLICATIONS or before pointing scrapers at any board beyond the one
we're testing with.
```

---

## 5. Handoff Instructions — Claude Cowork

Use these once the repo exists, for ongoing file/data upkeep (not code changes):

```
In the job-agent project folder:
1. Open config/master_profile.json and help me keep it current — when I give you
   updated resume bullets, certifications, or salary/visa preferences in chat,
   update this file directly, preserving its existing schema/keys.
2. When I export a new resume PDF or cover letter, file it under
   /exports/{company}_{role}_{date}/ and keep the folder names consistent.
3. Periodically summarize database/job_agent.db (or the Supabase table export I
   drop in /reports/) into a plain-language weekly status digest: how many jobs
   scanned, matched, applied, closed.
4. Never modify anything under /automation, /api, /scrapers, or /llm — those are
   code and should only change via Claude Code.
```

---

## 6. Open decisions before build starts
- Confirm `AUTO_SUBMIT_APPLICATIONS` should default **off** (recommended) so Playwright only pre-fills and opens the form for you to review and submit yourself, given ATS automated-submission ToS risk.
- Confirm which 2–3 companies' career boards to pilot against before scaling scraper coverage.
