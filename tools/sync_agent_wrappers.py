#!/usr/bin/env python3
"""Generate the Gemini CLI command wrappers in .gemini/commands/ from the workflow specs.

The workflow specifications live once, in `.claude/commands/*.md` and
`.claude/skills/{job-scraper,upskill}/SKILL.md`. Gemini CLI custom commands are TOML
files whose prompt can inline a file with `@{path}` and take the typed text as
`{{args}}`, so each wrapper is a few lines that point at the spec - the spec is never
copied, so the two cannot drift.

Run from anywhere:
    python3 tools/sync_agent_wrappers.py            # write the wrappers
    python3 tools/sync_agent_wrappers.py --check    # exit 1 if any are stale or missing (CI)
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / ".gemini" / "commands"

# Skills that act as slash commands. Their command name differs from the folder name.
SKILL_COMMANDS = {
    "scrape": (".claude/skills/job-scraper/SKILL.md", "Find new job postings across the installed portals"),
    "upskill": (".claude/skills/upskill/SKILL.md", "Skill-gap analysis and learning plan"),
}

TEMPLATE = """\
description = {description}
prompt = '''
Run the `{name}` workflow of this repository.

Follow the specification below step by step. Wherever it refers to `$ARGUMENTS`, the
user's input is: {{{{args}}}}

If the specification names a Claude Code tool or a subagent you do not have, use the
mapping in AGENTS.md ("If your agent is not Claude Code").

@{{{spec}}}
'''
"""


def toml_string(value: str) -> str:
    """A TOML basic string for a short single-line value."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def command_specs() -> dict[str, tuple[str, str]]:
    """name -> (spec path relative to the repo root, one-line description)."""
    specs: dict[str, tuple[str, str]] = {}
    for md in sorted((ROOT / ".claude" / "commands").glob("*.md")):
        first = md.read_text(encoding="utf-8").splitlines()[0]
        m = re.match(r"#\s*/\S+\s*[-:]\s*(.+)$", first)
        description = m.group(1).strip() if m else f"Run the {md.stem} workflow"
        specs[md.stem] = (f".claude/commands/{md.name}", description)
    for name, (rel, description) in SKILL_COMMANDS.items():
        if not (ROOT / rel).is_file():
            raise SystemExit(f"sync_agent_wrappers: missing spec {rel}")
        specs[name] = (rel, description)
    return specs


def render(name: str, spec: str, description: str) -> str:
    return TEMPLATE.format(name=name, spec=spec, description=toml_string(description))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--check", action="store_true", help="fail if wrappers are stale instead of writing them")
    args = parser.parse_args()

    expected = {f"{name}.toml": render(name, spec, desc) for name, (spec, desc) in command_specs().items()}
    stale: list[str] = []
    for filename, content in expected.items():
        path = OUT / filename
        if not path.exists() or path.read_text(encoding="utf-8") != content:
            stale.append(filename)
    extra = sorted(p.name for p in OUT.glob("*.toml") if p.name not in expected) if OUT.exists() else []

    if args.check:
        if stale or extra:
            for f in stale:
                print(f"sync_agent_wrappers: .gemini/commands/{f} is missing or out of date")
            for f in extra:
                print(f"sync_agent_wrappers: .gemini/commands/{f} has no matching spec")
            print("run: python3 tools/sync_agent_wrappers.py")
            return 1
        print(f"sync_agent_wrappers: OK ({len(expected)} wrappers)")
        return 0

    OUT.mkdir(parents=True, exist_ok=True)
    for filename, content in expected.items():
        (OUT / filename).write_text(content, encoding="utf-8", newline="\n")
    for f in extra:
        (OUT / f).unlink()
    print(f"sync_agent_wrappers: wrote {len(expected)} wrappers to .gemini/commands/ ({len(stale)} changed, {len(extra)} removed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
