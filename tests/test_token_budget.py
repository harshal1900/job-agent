"""Guards for tools/token_budget.py: the prompt files an agent loads stay within budget."""

import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "token_budget.py"
BUDGET = REPO / "tools" / "token_budget.json"


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True, cwd=REPO)


class TokenBudgetTests(unittest.TestCase):
    def test_every_prompt_file_is_within_its_ceiling(self):
        result = run("--check")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_report_runs_and_lists_the_workflows(self):
        result = run()
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in ("apply", "rank", "scrape", "interview", "setup"):
            self.assertIn(name, result.stdout)

    def test_always_loaded_files_stay_small(self):
        # CLAUDE.md is injected into every Claude Code turn, so it carries the profile and
        # pointers only. The long checklist and workflow detail load on demand.
        self.assertLess((REPO / "CLAUDE.md").stat().st_size, 6500)

    def test_budget_headroom_is_small(self):
        # A ceiling far above the real size would defeat the check.
        budget = json.loads(BUDGET.read_text(encoding="utf-8"))
        for rel, cap in budget["files"].items():
            size = (REPO / rel).stat().st_size
            self.assertLessEqual(cap, size * 1.25 + 200, f"{rel}: ceiling {cap} is loose for a {size}-byte file; run --update")

    def test_an_unlisted_file_fails_the_check(self):
        extra = REPO / ".claude" / "commands" / "zz_budget_probe.md"
        extra.write_text("# probe\n", encoding="utf-8")
        try:
            result = run("--check")
        finally:
            extra.unlink()
        self.assertEqual(result.returncode, 1)
        self.assertIn("zz_budget_probe.md", result.stdout)

    def test_a_file_over_its_ceiling_fails_the_check(self):
        original = BUDGET.read_text(encoding="utf-8")
        data = json.loads(original)
        data["files"]["AGENTS.md"] = 100
        BUDGET.write_text(json.dumps(data), encoding="utf-8")
        try:
            result = run("--check")
        finally:
            BUDGET.write_text(original, encoding="utf-8")
        self.assertEqual(result.returncode, 1)
        self.assertIn("AGENTS.md", result.stdout)


if __name__ == "__main__":
    unittest.main()
