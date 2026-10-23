"""The CSV export carries every stored field, in a stable order, safe for spreadsheets."""

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "tools" / "export_jobs_csv.py"

JOBS = {
    "a-1": {
        "title": "ML Engineer", "company": "Acme", "url": "https://x.test/a", "first_seen": "2026-10-20",
        "posted_date": "2026-10-19", "deadline": None, "fit": "high", "status": "ranked", "portal": "ats-search",
        "source": "cli", "location": "Dallas, TX", "salary": "$150K - $200K", "workplace": "hybrid",
        "rank_score": 82, "rank_verdict": "strong fit", "requirements": ["Python", "AWS"],
        "summary": "Build\nmodels.", "country": "US",
    },
    "b-2": {
        "title": "=HYPERLINK(\"http://evil.test\",\"click\")", "company": "Beta", "url": "https://x.test/b",
        "first_seen": "2026-10-22", "posted_date": None, "deadline": None, "fit": "medium", "status": "new",
        "portal": "linkedin-search", "source": "cli", "location": "Remote - US", "custom_field": "extra",
    },
    "c-3": {
        "title": "Data Analyst", "company": "Gamma", "url": "https://x.test/c", "first_seen": "2026-10-01",
        "posted_date": None, "deadline": None, "fit": "low", "status": "skipped", "portal": "freehire-search",
        "source": "cli",
    },
}


class ExportJobsCsvTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)
        self.state = self.dir / "seen_jobs.json"
        self.state.write_text(json.dumps({"seen": JOBS}), encoding="utf-8")
        self.out = self.dir / "out.csv"

    def run_tool(self, *extra):
        result = subprocess.run(
            [sys.executable, str(TOOL), "--state", str(self.state), "--out", str(self.out), *extra],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def rows(self):
        with self.out.open(encoding="utf-8-sig", newline="") as fh:
            return list(csv.DictReader(fh))

    def test_exports_every_job_with_all_fields_and_extras(self):
        report = self.run_tool()
        self.assertEqual(report["rows"], 3)
        rows = self.rows()
        first = rows[0]
        self.assertEqual(first["key"], "a-1")
        self.assertEqual(first["salary"], "$150K - $200K")
        self.assertEqual(first["requirements"], "Python; AWS")
        self.assertEqual(first["summary"], "Build models.", "newlines collapse so a row stays one line")
        self.assertIn("custom_field", rows[0].keys(), "unknown scalar fields become extra columns")
        self.assertEqual([r["key"] for r in rows if r["custom_field"]], ["b-2"])

    def test_ranked_first_then_fit_then_newest(self):
        self.run_tool()
        self.assertEqual([r["key"] for r in self.rows()], ["a-1", "b-2", "c-3"])

    def test_formulas_are_neutralised(self):
        self.run_tool()
        title = next(r for r in self.rows() if r["key"] == "b-2")["title"]
        self.assertTrue(title.startswith("'="), title)

    def test_selection_filters(self):
        self.assertEqual(self.run_tool("--keys", "c-3,a-1")["rows"], 2)
        self.assertEqual(self.run_tool("--status", "new")["rows"], 1)
        self.assertEqual(self.run_tool("--since", "2026-10-20")["rows"], 2)
        self.assertEqual(self.run_tool("--min-score", "80")["rows"], 1)

    def test_keys_file_accepts_scrape_store_output(self):
        kf = self.dir / "added.json"
        kf.write_text(json.dumps({"added": ["b-2"], "already_seen": 4}), encoding="utf-8")
        self.assertEqual(self.run_tool("--keys-file", str(kf))["rows"], 1)
        self.assertEqual(self.rows()[0]["key"], "b-2")

    def test_bom_and_empty_selection_still_write_a_header(self):
        self.assertEqual(self.run_tool("--keys", "nope")["rows"], 0)
        raw = self.out.read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        self.assertIn(b"title", raw.splitlines()[0])

    def test_missing_state_is_a_clear_error(self):
        self.state.unlink()
        result = subprocess.run(
            [sys.executable, str(TOOL), "--state", str(self.state), "--out", str(self.out)],
            capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("run /scrape first", result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
