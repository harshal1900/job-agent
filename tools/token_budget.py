#!/usr/bin/env python3
"""Size budgets for the prompt files an agent loads, so the workflow cannot silently bloat.

Every Markdown file an agent can be asked to read (CLAUDE.md, AGENTS.md, everything
under .claude/) must be listed in tools/token_budget.json with a byte ceiling, and the
files each workflow loads together have a combined ceiling. Tokens are estimated as
bytes / 4, which is close enough to compare files and catch growth; it is not a
tokenizer.

    python3 tools/token_budget.py            # report: size, budget, estimated tokens
    python3 tools/token_budget.py --check    # exit 1 on an unlisted file or a breached budget (CI)
    python3 tools/token_budget.py --update   # set every ceiling to the current size plus headroom

Raising a ceiling is a deliberate act: --update shows up as a diff in review.
"""

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUDGET_FILE = ROOT / "tools" / "token_budget.json"
BYTES_PER_TOKEN = 4
HEADROOM = 1.05  # new ceilings are the current size plus 5%, rounded up to 100 bytes


def discover() -> list[str]:
    files = ["CLAUDE.md", "AGENTS.md"] + [p.relative_to(ROOT).as_posix() for p in sorted((ROOT / ".claude").rglob("*.md"))]
    return files


def size(rel: str) -> int:
    # Count line breaks as one byte so a Windows checkout (CRLF) matches the ceilings.
    return len((ROOT / rel).read_bytes().replace(b"\r\n", b"\n"))


def tokens(nbytes: int) -> int:
    return math.ceil(nbytes / BYTES_PER_TOKEN)


def ceiling(nbytes: int) -> int:
    return int(math.ceil(nbytes * HEADROOM / 100.0) * 100)


def load() -> dict:
    return json.loads(BUDGET_FILE.read_text(encoding="utf-8"))


def check(budget: dict) -> list[str]:
    errors: list[str] = []
    listed = budget["files"]
    for rel in discover():
        if rel not in listed:
            errors.append(f"{rel}: not in tools/token_budget.json (run --update after deciding it belongs)")
        elif size(rel) > listed[rel]:
            errors.append(f"{rel}: {size(rel)} bytes exceeds its ceiling of {listed[rel]} (~{tokens(size(rel))} tokens)")
    for rel in listed:
        if not (ROOT / rel).is_file():
            errors.append(f"{rel}: listed in tools/token_budget.json but does not exist")
    for name, wf in budget["workflows"].items():
        for rel in wf["files"]:
            if not (ROOT / rel).is_file():
                errors.append(f"workflow {name}: {rel} does not exist")
        total = sum(size(rel) for rel in wf["files"] if (ROOT / rel).is_file())
        if total > wf["max_bytes"]:
            errors.append(f"workflow {name}: {total} bytes (~{tokens(total)} tokens) exceeds {wf['max_bytes']}")
    return errors


def report(budget: dict) -> None:
    print(f"{'file':72} {'bytes':>7} {'ceiling':>8} {'~tokens':>8}")
    for rel in discover():
        cap = budget["files"].get(rel)
        print(f"{rel:72} {size(rel):>7} {cap if cap is not None else '-':>8} {tokens(size(rel)):>8}")
    print()
    print(f"{'workflow (files loaded together)':40} {'bytes':>7} {'ceiling':>8} {'~tokens':>8}")
    for name, wf in budget["workflows"].items():
        total = sum(size(rel) for rel in wf["files"])
        print(f"{name:40} {total:>7} {wf['max_bytes']:>8} {tokens(total):>8}")


def update(budget: dict) -> dict:
    budget["files"] = {rel: ceiling(size(rel)) for rel in discover()}
    for wf in budget["workflows"].values():
        wf["max_bytes"] = ceiling(sum(size(rel) for rel in wf["files"]))
    return budget


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--update", action="store_true")
    args = parser.parse_args()
    budget = load()
    if args.update:
        BUDGET_FILE.write_text(json.dumps(update(budget), indent=2) + "\n", encoding="utf-8", newline="\n")
        print(f"token_budget: updated {BUDGET_FILE.relative_to(ROOT)}")
        return 0
    if args.check:
        errors = check(budget)
        for e in errors:
            print(f"token_budget: {e}")
        if errors:
            return 1
        print(f"token_budget: OK ({len(discover())} files, {len(budget['workflows'])} workflows)")
        return 0
    report(budget)
    return 0


if __name__ == "__main__":
    sys.exit(main())
