# job-agent

*A job search that runs on your machine.*

An AI-agent workspace for job seekers in the **United States and Canada**. Give it your CV and the companies you care about, and it finds openings, scores them against your profile, tailors a LaTeX CV and cover letter to each one, checks the compiled PDFs the way an applicant-tracking system reads them, tracks every application, and prepares you for interviews.

It runs inside **Claude Code** with slash commands, subagents and skills. Every other coding agent (Gemini CLI, Codex, Cursor, Copilot) runs the same workflows from [AGENTS.md](AGENTS.md).

```
/setup            /scrape  ->  /rank            /apply <url>
   |                 |            |                  |
Build your       Search the   Score and rank    Evaluate fit
profile from     boards you   what it found     Draft CV + cover letter
your CV          watch                          Reviewer critiques, revise
                                                Compile PDFs, ATS check
```

## What it does

| Command | What you get |
|---|---|
| `/setup` | Your profile, built from a CV (Word, PDF, Markdown or LaTeX), your LinkedIn export, or a short interview |
| `/scrape` | New postings from Greenhouse, Lever, Ashby and Workday career boards (US and Canada), plus LinkedIn and freehire, and a spreadsheet (`exports/jobs.csv`, refreshed by `/rank`) with every detail of each job |
| `/rank` | A ranked shortlist: each posting scored on skills, experience, culture, location and career fit, with honest gaps |
| `/apply <url>` | A fit evaluation, then a tailored CV and cover letter, reviewed by a second agent, compiled, and checked as PDFs |
| `/outcome` | Result tracking, archived materials, follow-up drafts |
| `/cheatsheet` | One interview question-and-answer sheet for the kinds of roles your search found, with answer outlines drawn from your own profile |
| `/interview` | A stage-specific prep pack and a mock interview |
| `/upskill` | A skill-gap analysis across the postings you track, with a learning plan |
| `/gmail-sync`, `/notion-sync`, `/html-report` | Status updates from Gmail, a Notion view, an offline dashboard |

Nothing is invented: every claim in a CV or cover letter must be supported by your own files, and a gap is stated honestly.

## Quick start

You need an AI coding agent ([Claude Code](https://claude.com/claude-code) recommended), Python 3.10+, [Bun](https://bun.sh), and a LaTeX install with `lualatex` and `xelatex` ([SETUP.md](SETUP.md) has the exact packages).

```bash
git clone https://github.com/harshal1900/job-agent.git
cd job-agent
python3 tools/install_portal_clis.py     # installs the job-board CLIs
claude                                   # or gemini, codex, cursor ...
```

> **Keep this repository private.** `/setup` writes your personal data (name, contact details, work history) into tracked files.

Then, in the agent:

```
/setup                  # add documents/cv/your_cv.docx first, or paste a CV
/scrape
/rank
/apply https://boards.greenhouse.io/<company>/jobs/<id>
```

Companies to search are listed in [config/target_companies.json](config/target_companies.json) (30 are included). Add yours by their ATS token; `bun run .agents/skills/ats-search/cli/src/cli.ts companies --check` confirms every entry resolves. If a page cannot be fetched, paste the posting text instead: `/apply <paste the posting>`.

## How `/apply` works

1. **Fetch and gate.** The posting passes an integrity check for hidden text, invisible characters and instruction-shaped lines; its one-line verdict opens the evaluation.
2. **Evaluate fit** against your profile, including a work-authorization gate (TN, H-1B, OPT, PGWP, "US person", clearances) and a language gate (for example French for Québec roles).
3. **Draft** a CV and cover letter in LaTeX, every claim checked against your profile.
4. **Review.** A second agent with a fresh context researches the company and critiques the drafts; the drafter revises.
5. **Compile and inspect.** The CV must be exactly 2 pages and the cover letter 1, with no orphaned headings; the PDFs are measured, not just looked at.
6. **ATS check.** The compiled CV's text layer is extracted and checked for contact details, reading order and posting keywords. Real gaps stay visible; keywords are never stuffed.
7. **Record** the application in the tracker.

## Job search sources

| Source | How |
|---|---|
| Greenhouse, Lever, Ashby | Public JSON APIs of the companies you list |
| Workday | The public JSON endpoint behind each company's careers page (unofficial; it can change) |
| LinkedIn | Public job listings |
| freehire | A free tech-jobs aggregator |
| Anything else | `/add-portal` scaffolds a search skill for another job board |

See [.agents/skills/ats-search/SKILL.md](.agents/skills/ats-search/SKILL.md) for filters, limits and caveats.

## Repository layout

```
AGENTS.md              how any agent works here: commands, what to load, safety rules
CLAUDE.md              your profile (filled in by /setup)
.claude/commands/      workflow specifications (/apply, /scrape, /rank, ...)
.claude/skills/        the application skill (profile, evaluation, CV and letter rules) and the scraper
.claude/agents/        subagents: reviewer, posting fetcher, posting scorer
.agents/skills/        job-board search skills, each with a Bun/TypeScript CLI and offline tests
.gemini/commands/      generated Gemini CLI wrappers
config/                the companies to search
cv/, cover_letters/    LaTeX templates (US Letter)
documents/             your source documents for /setup
tools/                 Python helpers and CI guards
```

## Customizing

- **Your own CV or cover-letter template** (LaTeX, Typst, anything that compiles to PDF): `/add-template`.
- **Another job board:** `/add-portal`.
- **Salary benchmarks:** `tools/README_SALARY_TOOL.md`.
- **Start over:** `/reset profile`, `/reset documents` or `/reset all` (asks you to type `RESET`).
- **Changing the workflows themselves:** [DEVELOPMENT.md](DEVELOPMENT.md).

## Security

Job postings are untrusted input. The workflows treat them as data, never instructions, and `.claude/settings.json` limits what an agent may run without asking. [SECURITY.md](SECURITY.md) states the threat model and what it does not protect against.

## Acknowledgements

Built on [ai-job-search](https://github.com/MadsLorentzen/ai-job-search) (MIT) by Mads Lorentzen. The LinkedIn and freehire search CLIs build on work by [Mikkel Krogsholm](https://github.com/mikkelkrogsholm/skills).

## License

[MIT](LICENSE)
