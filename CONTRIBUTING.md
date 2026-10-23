# Contributing

This is a private project. These notes are for anyone (human or agent) changing it.

## Before you change anything

Read [DEVELOPMENT.md](DEVELOPMENT.md): it explains the layout, the rules for editing the workflow specs (keep them lean, regenerate the Gemini wrappers, respect the token budgets) and lists the checks.

## What a good change looks like

- **One concern per change**, with a commit message that says why.
- **Reproduce before you fix.** State the failing case and run it on the real path the workflow takes, not an input you built to fit the fix.
- **Add a test that fails without the change.** Python tool tests go in `tests/`; portal CLI tests go in `.agents/skills/<name>/cli/tests/` and must pass with no network.
- **Specs are the implementation.** The workflow lives once, in `.claude/`. Do not copy a spec into another place; point at it (see `tools/sync_agent_wrappers.py`).
- **New commands face a high bar.** Add one only when it operationalizes something error-prone that already exists, not for a hypothetical need.
- **Security-relevant files prompt for approval on purpose** (`.claude/settings.json`, skills, commands, agents, `.github/**`). A new portal CLI needs its own allow-list entry in `.claude/settings.json` and `tools/security_guards.py`.

## Run what CI runs

```bash
python3 -m pytest tests
python3 tools/lint_skills.py
python3 tools/security_guards.py
python3 tools/sync_agent_wrappers.py --check
python3 tools/token_budget.py --check
# in each touched portal CLI folder (.agents/skills/<name>/cli):
bun install && bun run typecheck && bun test
```

Never commit personal data (CV, profile, tracker, `.env`). Reproducing a bug with a real posting or CV means redacting it first.
