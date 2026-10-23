"""The cheat-sheet brief picks the right jobs, groups roles and counts skills."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "tools" / "cheatsheet_input.py"
sys.path.insert(0, str(ROOT / "tools"))
import cheatsheet_input as ci  # noqa: E402


def job(title, company, **extra):
    base = {"title": title, "company": company, "url": f"https://x.test/{company}/{title}", "first_seen": "2026-10-20",
            "fit": "high", "status": "new", "portal": "ats-search", "source": "cli"}
    base.update(extra)
    return base


JOBS = {
    "1": job("Senior ML Engineer, Search - Remote (US)", "Acme", rank_score=90, status="ranked",
             requirements=["5+ years of Python", "Experience with AWS and Kubernetes"], summary="Build ranking models with PyTorch."),
    "2": job("ML Engineer", "Beta", rank_score=70, status="ranked", requirements=["Python and SQL", "Experience with AWS and Kubernetes"]),
    "3": job("Staff Backend Engineer", "Gamma", rank_score=60, status="ranked", requirements=["Go or Java"]),
    "4": job("Data Analyst", "Delta", rank_score=20, status="ranked"),
    "5": job("ML Engineer", "Old", rank_score=99, status="expired"),
}


class Args:
    def __init__(self, **kw):
        self.__dict__.update({"top": 10, "min_score": None, "keys": None, "role": None, **kw})


class CheatsheetInputTests(unittest.TestCase):
    def test_core_title_drops_seniority_location_and_team(self):
        self.assertEqual(ci.core_title("Senior ML Engineer, Search - Remote (US)"), "ml engineer")
        self.assertEqual(ci.core_title("Staff Software Engineer II"), "software engineer")
        self.assertEqual(ci.core_title("Lead"), "lead", "a title that is only seniority words is kept")

    def test_pick_uses_rank_order_top_and_min_score_and_skips_expired(self):
        keys = [k for k, _ in ci.pick(JOBS, Args(top=3))]
        self.assertEqual(keys, ["1", "2", "3"])
        self.assertNotIn("5", keys)
        self.assertEqual([k for k, _ in ci.pick(JOBS, Args(min_score=65))], ["1", "2"])

    def test_pick_falls_back_to_quick_fit_when_nothing_is_ranked(self):
        unranked = {"a": job("X Engineer", "A", fit="medium"), "b": job("Y Engineer", "B", fit="high"),
                    "c": job("Z Engineer", "C", fit="low"), "d": job("W Engineer", "D", fit="high", status="skipped")}
        self.assertEqual([k for k, _ in ci.pick(unranked, Args())], ["b", "a"])

    def test_role_filter_and_explicit_keys(self):
        self.assertEqual([k for k, _ in ci.pick(JOBS, Args(role="backend"))], ["3"])
        self.assertEqual({k for k, _ in ci.pick(JOBS, Args(keys="4,5"))}, {"4"}, "an expired posting is never prepared for")

    def test_brief_groups_roles_and_counts_terms_by_job(self):
        brief = ci.build(ci.pick(JOBS, Args(top=3)))
        self.assertEqual(brief["jobs_considered"], 3)
        ml = next(f for f in brief["families"] if f["role"] == "ml engineer")
        self.assertEqual(ml["count"], 2)
        self.assertEqual(ml["companies"], ["Acme", "Beta"])
        terms = {t["term"]: t["jobs"] for t in ml["top_terms"]}
        self.assertEqual(terms["python"], 2)
        self.assertEqual(terms["aws"], 2)
        self.assertEqual(terms["pytorch"], 1)
        self.assertEqual(len(ml["requirements"]), 3, "duplicate requirement lines collapse")
        self.assertIn("untrusted", brief["note"])

    def test_term_matching_respects_word_boundaries(self):
        got = ci.count_terms(["JavaScript developer", "Java developer", "Django app", "going forward", "C++ and C#"])
        self.assertEqual({t["term"]: t["jobs"] for t in got},
                         {"c#": 1, "c++": 1, "django": 1, "java": 1, "javascript": 1})

    def test_cli_prints_json_and_fails_cleanly_with_no_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "s.json"
            state.write_text(json.dumps({"seen": JOBS}), encoding="utf-8")
            ok = subprocess.run([sys.executable, str(TOOL), "--state", str(state), "--top", "2"], capture_output=True, text=True)
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertEqual(json.loads(ok.stdout)["jobs_considered"], 2)
            bad = subprocess.run([sys.executable, str(TOOL), "--state", str(state), "--role", "zzz"], capture_output=True, text=True)
            self.assertEqual(bad.returncode, 1)
            self.assertIn("no matching jobs", bad.stderr)


if __name__ == "__main__":
    unittest.main()
