"""Guards for the multi-agent entry points: AGENTS.md, GEMINI.md and the generated
Gemini CLI command wrappers in .gemini/commands/.

The workflow specs live once under .claude/. The wrappers only point at them, and
these tests keep the pointers honest: every spec has a wrapper, every wrapper parses
as TOML and inlines a spec that exists, and AGENTS.md lists every command and only
names files that exist.
"""

import re
import subprocess
import sys
import unittest
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # Python 3.10
    tomllib = None

REPO = Path(__file__).resolve().parent.parent
AGENTS = REPO / "AGENTS.md"
WRAPPERS = REPO / ".gemini" / "commands"
SYNC = REPO / "tools" / "sync_agent_wrappers.py"


def spec_names() -> set[str]:
    names = {p.stem for p in (REPO / ".claude" / "commands").glob("*.md")}
    return names | {"scrape", "upskill"}


class WrapperTests(unittest.TestCase):
    def test_wrappers_are_in_sync_with_the_specs(self):
        result = subprocess.run([sys.executable, str(SYNC), "--check"], capture_output=True, text=True, cwd=REPO)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_every_spec_has_exactly_one_wrapper(self):
        self.assertEqual({p.stem for p in WRAPPERS.glob("*.toml")}, spec_names())

    @unittest.skipIf(tomllib is None, "tomllib needs Python 3.11+")
    def test_each_wrapper_is_valid_toml_that_inlines_an_existing_spec(self):
        for path in sorted(WRAPPERS.glob("*.toml")):
            with self.subTest(wrapper=path.name):
                doc = tomllib.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(set(doc), {"description", "prompt"})
                self.assertTrue(doc["description"].strip())
                self.assertIn("{{args}}", doc["prompt"])
                refs = re.findall(r"@\{([^}]+)\}", doc["prompt"])
                self.assertEqual(len(refs), 1, "one inlined spec per wrapper")
                self.assertTrue((REPO / refs[0]).is_file(), f"{refs[0]} does not exist")
                self.assertFalse(refs[0].startswith("/") or ".." in refs[0], "path must stay inside the workspace")

    def test_wrapper_does_not_copy_the_spec(self):
        for path in WRAPPERS.glob("*.toml"):
            self.assertLess(len(path.read_text(encoding="utf-8")), 800, f"{path.name} should only point at its spec")


class EntryPointTests(unittest.TestCase):
    def setUp(self):
        self.text = AGENTS.read_text(encoding="utf-8")

    def test_gemini_md_imports_agents_md(self):
        self.assertEqual((REPO / "GEMINI.md").read_text(encoding="utf-8").strip(), "@./AGENTS.md")

    def test_copilot_instructions_point_at_agents_md(self):
        self.assertIn("AGENTS.md", (REPO / ".github" / "copilot-instructions.md").read_text(encoding="utf-8"))

    def test_agents_md_lists_every_command(self):
        for name in sorted(spec_names()):
            self.assertRegex(self.text, rf"\|\s*`{re.escape(name)}[ `]", f"AGENTS.md command table is missing {name}")

    def test_every_path_in_agents_md_exists(self):
        missing = []
        for ref in sorted(set(re.findall(r"`((?:\.claude|\.agents|tools|config|cv|cover_letters)/[^`\s]+)`", self.text))):
            if any(c in ref for c in "*<>"):
                continue
            if not (REPO / ref.rstrip("/")).exists():
                missing.append(ref)
        self.assertEqual(missing, [], f"AGENTS.md names files that do not exist: {missing}")

    def test_skill_file_names_in_agents_md_exist(self):
        skill_dir = REPO / ".claude" / "skills" / "job-application-assistant"
        for name in re.findall(r"`(\d\d-[a-z-]+\.md)`", self.text):
            self.assertTrue((skill_dir / name).is_file(), f"{name} is not in {skill_dir}")

    def test_agents_md_covers_every_subagent_role(self):
        for agent in (REPO / ".claude" / "agents").glob("*.md"):
            self.assertIn(f"`{agent.stem}`", self.text, f"AGENTS.md has no fallback for {agent.stem}")
            self.assertIn(f".claude/agents/{agent.name}", self.text)

    def test_agents_md_stays_small(self):
        # AGENTS.md is read by every non-Claude agent on every session.
        self.assertLess(len(self.text), 9000, "AGENTS.md has grown past its budget; move detail into a spec")


if __name__ == "__main__":
    unittest.main()
