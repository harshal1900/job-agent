# Autonomous AI Job Search & Application Agent

Local, zero-infra-cost agent that discovers matching jobs, tailors resume/cover
letter drafts, gets your approval by email, and (optionally) submits the
application. Full spec: [`docs/PRD.md`](docs/PRD.md).

## Non-negotiables

- **Human-in-the-loop.** Nothing is submitted without an explicit approval
  click, confirmed via a POST landing page (not a bare email link).
- **`AUTO_SUBMIT_APPLICATIONS` defaults to `false`.** Playwright pre-fills
  the ATS form and opens a real browser window for you to review and submit
  yourself, until you explicitly flip a per-ATS flag on. See
  `config/settings.py: Settings.auto_submit_for`.
- **No hallucinated resume content.** `llm/resume_rewriter.py` can only
  reorder/reword facts already in `config/master_profile.json`; a mechanical
  guardrail flags any invented company/tool/number before an email is sent.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium

cp .env.example .env
# fill in .env: at minimum APPROVAL_TOKEN_SECRET, and either
# OPENROUTER_API_KEY or HF_API_TOKEN depending on LLM_PROVIDER
```

Generate a token secret:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

`config/master_profile.json` is **gitignored** (it holds your real name,
contact info, and work history) — it won't exist yet on a fresh clone.
Create it yourself with this structure, filled in with your real data; the
resume rewriter can only draw from what's in here, so the more complete it
is, the better the tailored drafts:

```json
{
  "personal_info": {
    "full_name": "",
    "email": "",
    "phone": "",
    "location": "",
    "linkedin": "",
    "languages": []
  },
  "work_authorization": {
    "status": "",
    "authorized_countries": [],
    "requires_sponsorship": false,
    "notes": ""
  },
  "job_search_preferences": {
    "target_titles": [],
    "target_locations": [],
    "remote_preference": "remote_or_hybrid",
    "salary_floor_usd": 0,
    "years_of_experience": 0,
    "seniority_level": "",
    "industries_of_interest": []
  },
  "professional_summary": "",
  "core_ai_competencies": {
    "llms_genai": [],
    "rag_pipelines": [],
    "agentic_ai": [],
    "applied_ml": [],
    "nlp": [],
    "ai_augmented_dev": []
  },
  "technical_skills": {
    "ai_ml_engineering": [],
    "ai_augmented_development": [],
    "enterprise_architecture": [],
    "engineering_leadership": []
  },
  "ai_ml_projects": [
    {
      "name": "",
      "program": "",
      "status": "",
      "description": "",
      "skills_tools": []
    }
  ],
  "professional_experience": [
    {
      "title": "",
      "company": "",
      "location": "",
      "start_date": "",
      "end_date": "",
      "achievements": []
    }
  ],
  "education": [
    {
      "program": "",
      "institution": "",
      "status": "",
      "coverage": ""
    }
  ],
  "certifications": [
    {
      "name": "",
      "issuer": "",
      "year": ""
    }
  ]
}
```

The section names above aren't hardcoded anywhere — `llm/resume_rewriter.py`
and `llm/match_scorer.py` just flatten every string value in this file into
a fact vocabulary, so you can add/rename fields as long as you keep it
valid JSON.

Add one pilot company board to `config/target_boards.yaml` (Greenhouse only
for now; Lever/Workday scrapers are stubs — see `scrapers/`).

## Running locally

```bash
# one-off pipeline runs, no server needed:
python manage.py init-db
python manage.py scan            # discover + score + tailor + email
python manage.py check-status    # 24h closed-posting sweep

# after you click Approve in the email and confirm on the landing page:
python manage.py run-application <application_id>

# full server (scheduler + /respond approval endpoints):
uvicorn api.main:app --reload
```

Expose `/respond` publicly only during an approval window, e.g.:

```bash
ngrok http 8000
```

then set `PUBLIC_BASE_URL` in `.env` to the ngrok URL before running a scan
(it's baked into the email links at send time).

## Tests

```bash
pytest
```

## Project layout

See `docs/PRD.md` §3 for the full annotated file tree. Key modules:

- `config/settings.py` — env loading + feature flags
- `database/` — SQLAlchemy models (SQLite by default, Supabase-compatible)
- `scrapers/` — one scraper per ATS (Greenhouse implemented; Lever/Workday
  are stubs, add after the Greenhouse pilot works end-to-end)
- `llm/` — matching, anti-hallucination-guarded rewriting, interview prep
- `api/security.py` — signed, single-use, expiring approval tokens
- `api/routes_approval.py` — GET landing page / POST confirm split, so
  email link-scanners can't silently consume an approval
- `automation/` — Playwright form-fill + 24h status checker
