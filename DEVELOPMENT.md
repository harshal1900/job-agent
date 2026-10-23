# Developing job-agent

How to change this repository without breaking it. Day-to-day use is in [AGENTS.md](AGENTS.md).

## Layout

| Path | What it is |
|---|---|
| `.claude/commands/*.md`, `.claude/skills/*/SKILL.md` | The workflow specifications: the single source of truth for every agent |
| `.claude/agents/*.md` | Subagent definitions (the reviewer's whole task list lives here) |
| `.agents/skills/*/` | Job-portal search skills, each with a Bun/TypeScript CLI |
| `.gemini/commands/*.toml` | **Generated** Gemini CLI wrappers; never edit by hand |
| `tools/` | Python helpers the workflows call, plus the CI guards |
| `config/target_companies.json` | The companies `ats-search` watches |
| `cv/`, `cover_letters/` | LaTeX templates |

## Rules when editing a spec

1. **Keep prompt files lean.** They are read by an agent on every run. Put rarely needed detail in a
   file that is loaded on demand (see `05b-cv-layout-and-ats.md`, `04b-company-research-and-calls.md`)
   and say in the spec exactly when to load it.
2. **Run `python3 tools/token_budget.py`** to see sizes. A file or workflow over its ceiling fails
   CI. If growth is justified, run `python3 tools/token_budget.py --update` and say why in the commit.
3. **After adding or renaming a command or skill, run `python3 tools/sync_agent_wrappers.py`** and
   add it to the command table in `AGENTS.md`. A test fails if either is missed.
4. **A new portal CLI needs its own allow-list entry** in `.claude/settings.json` and
   `tools/security_guards.py`. Use `/add-portal`; it follows the portal contract in `add-portal.md`.
5. Specs are written for an agent that has not seen the repo: say what to read, what to run, and
   what "done" looks like. Never rely on conversation context.

## Checks (all run in CI)

```bash
python3 -m pytest tests                        # specs, tools and guards
python3 tools/lint_skills.py                   # skill/command/settings structure
python3 tools/security_guards.py               # permission allow-list and tool grants
python3 tools/sync_agent_wrappers.py --check   # Gemini wrappers match the specs
python3 tools/token_budget.py --check          # prompt-file size budgets
for d in .agents/skills/*/cli; do (cd $d && bun install && bun run typecheck && bun test); done
```

The portal CLI tests are offline (a local mock server plus captured API responses); none of them
touches a live job site.
