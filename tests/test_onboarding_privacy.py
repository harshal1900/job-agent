"""Guards for the onboarding privacy warnings.

/setup writes personal data (name, contact details, employment history) into
tracked files. These tests pin that the warning to keep the repository private
lives at the point of decision (next to the clone command in README.md and
SETUP.md) and that /setup checks the origin's visibility BEFORE writing
anything, not in its closing notes.
"""
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
README = REPO / "README.md"
SETUP_GUIDE = REPO / "SETUP.md"
SETUP_COMMAND = REPO / ".claude" / "commands" / "setup.md"


def section(text: str, heading: str) -> str:
    """Body of a markdown section up to the next heading of the same level."""
    level = heading.split(" ")[0]
    pattern = re.compile(
        rf"^{re.escape(heading)}\n(.*?)(?=^{level} |\Z)", re.MULTILINE | re.DOTALL
    )
    match = pattern.search(text)
    return match.group(1) if match else ""


class TestPrivacyWarningsAtTheDecisionPoint(unittest.TestCase):
    """/setup writes personal data into tracked files, so the warning to keep the
    repository private sits next to the clone command, where the user decides."""

    def assert_warns(self, body: str, where: str):
        self.assertRegex(body, re.compile(r"private", re.IGNORECASE), f"{where} must say to keep the repository private")
        self.assertIn("personal data", body, f"{where} must say /setup writes personal data into tracked files")

    def test_readme_quick_start_warns_next_to_the_clone_command(self):
        text = README.read_text(encoding="utf-8")
        start = text.index("git clone ")
        self.assert_warns(text[start : start + 1500], "README quick start")

    def test_setup_guide_warns_next_to_the_clone_command(self):
        body = section(SETUP_GUIDE.read_text(encoding="utf-8"), "## 2. Clone and keep it private")
        self.assertIn("git clone", body, "sanity: the clone command lives in this section")
        self.assert_warns(body, "SETUP.md")


class TestSetupChecksOriginBeforeWriting(unittest.TestCase):
    def test_preflight_exists_and_precedes_profile_generation(self):
        text = SETUP_COMMAND.read_text(encoding="utf-8")
        self.assertIn(
            "git remote get-url origin",
            text,
            "/setup must check where the working copy would publish to",
        )
        preflight_at = text.index("git remote get-url origin")
        writes_at = text.index("## Step 3: Generate Profile Files")
        self.assertLess(
            preflight_at,
            writes_at,
            "the origin check must run before any profile file is written - the "
            "existing Step 4 note fires after everything is already on disk",
        )
        self.assertIn(
            "public",
            text[max(0, preflight_at - 2000) : preflight_at + 2000].lower(),
            "the preflight must be about public visibility, not just remote presence",
        )


if __name__ == "__main__":
    unittest.main()
