#!/usr/bin/env python3
"""Export the jobs /scrape has stored to a CSV file that opens in Excel or Sheets.

Reads job_scraper/seen_jobs.json (never printed into the agent context) and writes
one row per job with every field the workflow stored: where it is, what it pays,
when it was posted, how well it fits, and the link. Pick rows with --keys (the
`added` keys /scrape prints), --since, --status or --min-score; with no selection
every stored job is exported.

    python3 tools/export_jobs_csv.py --keys-file added.json
    python3 tools/export_jobs_csv.py --since 2026-10-01 --status new,ranked

The default output is exports/jobs_<YYYY-MM-DD>.csv (exports/ is gitignored).
"""

import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path

from rank_state import ROOT, STATE, load_state

# Fixed columns come first, in the order a job-seeker reads them. Any other scalar
# fields a job carries (a portal may add its own) follow, sorted by name.
COLUMNS = [
    "key", "rank_score", "rank_verdict", "fit", "status", "title", "company", "location",
    "country", "workplace", "employment_type", "department", "salary", "posted_date",
    "deadline", "first_seen", "portal", "source", "url", "location_verdict", "language_gate",
    "requirements", "summary", "notes",
]
FIT_ORDER = {"high": 0, "medium": 1, "low": 2}
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def cell(value) -> str:
    """One CSV cell: single line, and never a spreadsheet formula."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, list):
        # Drop list-bullet markers ("- item", "• item") so they do not read as formulas.
        items = (" ".join(str(v).split()).lstrip("-•*· ").strip() for v in value if v not in (None, ""))
        value = "; ".join(i for i in items if i)
    text = " ".join(str(value).split())
    # A cell starting with = + - @ is run as a formula by Excel and Sheets. Job text
    # comes from the open web, so neutralize it with a leading apostrophe.
    if text.startswith(FORMULA_PREFIXES):
        text = "'" + text
    return text


def parse_keys(args) -> set | None:
    keys = set()
    if args.keys:
        keys |= {k.strip() for k in args.keys.split(",") if k.strip()}
    if args.keys_file:
        try:
            data = json.loads(Path(args.keys_file).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"cannot read {args.keys_file}: {exc}") from exc
        if isinstance(data, dict):
            data = data.get("added")
        if not isinstance(data, list):
            raise ValueError("keys file must be a JSON array, or an object with an 'added' array")
        keys |= {str(k) for k in data}
    return keys if (args.keys or args.keys_file) else None


def select(seen: dict, keys, statuses, since, min_score) -> list[tuple[str, dict]]:
    rows = []
    for key, entry in seen.items():
        if not isinstance(entry, dict):
            continue
        if keys is not None and key not in keys:
            continue
        if statuses and entry.get("status") not in statuses:
            continue
        if since and not (isinstance(entry.get("first_seen"), str) and entry["first_seen"] >= since):
            continue
        if min_score is not None:
            score = entry.get("rank_score")
            if not isinstance(score, (int, float)) or score < min_score:
                continue
        rows.append((key, entry))

    # Stable sorts from the least to the most important key: newest first, then
    # fit band, then rank score (ranked jobs ahead of unranked ones).
    rows.sort(key=lambda item: str(item[1].get("first_seen") or ""), reverse=True)
    rows.sort(key=lambda item: FIT_ORDER.get(item[1].get("fit"), 3))
    rows.sort(
        key=lambda item: -item[1]["rank_score"] if isinstance(item[1].get("rank_score"), (int, float)) else 1
    )
    return rows


def write_csv(rows: list[tuple[str, dict]], out: Path) -> int:
    extras = sorted(
        {
            k
            for _, e in rows
            for k, v in e.items()
            if k not in COLUMNS and not isinstance(v, dict)
        }
    )
    header = COLUMNS + extras
    out.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig: Excel on Windows and macOS opens accented text correctly only with a BOM.
    with out.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        for key, entry in rows:
            record = {"key": key, **entry}
            writer.writerow([cell(record.get(col)) for col in header])
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--keys", help="comma-separated job keys")
    parser.add_argument("--keys-file", help="JSON array of keys, or /scrape's store output with an 'added' array")
    parser.add_argument("--status", help="comma-separated statuses, e.g. new,ranked")
    parser.add_argument("--since", help="only jobs first seen on or after this date (YYYY-MM-DD)")
    parser.add_argument("--min-score", type=float, help="only ranked jobs with rank_score at or above this")
    parser.add_argument("--out", help="output path (default exports/jobs_<today>.csv)")
    parser.add_argument("--state", type=Path, default=STATE, help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        _, seen = load_state(args.state)
        rows = select(
            seen,
            parse_keys(args),
            {s.strip() for s in args.status.split(",")} if args.status else None,
            args.since,
            args.min_score,
        )
        out = Path(args.out) if args.out else ROOT / "exports" / f"jobs_{date.today().isoformat()}.csv"
        count = write_csv(rows, out)
    except (ValueError, OSError) as exc:
        print(f"export_jobs_csv: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"written": str(out), "rows": count}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
