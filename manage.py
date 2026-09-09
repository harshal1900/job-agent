"""Local CLI entrypoint — run pieces of the pipeline by hand without the
FastAPI server, e.g. for the first end-to-end pilot run (PRD build step 9).

Usage:
    python manage.py init-db
    python manage.py scan
    python manage.py check-status
    python manage.py run-application <application_id>

`run-application` is a separate CLI step (not a FastAPI request handler) on
purpose — see automation/playwright_runner.py: in manual mode it leaves a
real browser window open for you to review and click submit, which needs a
foreground process, not an async request/response cycle.
"""

from __future__ import annotations

import argparse
import logging
import sys

logging.basicConfig(level=logging.INFO)


def cmd_init_db(_args) -> None:
    from database.db import init_db

    init_db()
    print("Database initialized.")


def cmd_scan(_args) -> None:
    from database.db import init_db
    from api.scheduler import scan_job

    init_db()
    scan_job()
    print("Scan cycle complete.")


def cmd_check_status(_args) -> None:
    from database.db import init_db
    from automation.status_checker import check_job_statuses

    init_db()
    result = check_job_statuses()
    print(f"Checked {result['checked']} jobs, {result['newly_closed']} newly closed.")


def cmd_run_application(args) -> None:
    from database.db import init_db, session_scope
    from database.models import Application, Job
    from automation.playwright_runner import ApplicationPayload, PlaywrightRunner
    from config.settings import get_settings

    init_db()
    settings = get_settings()

    with session_scope() as session:
        application = session.get(Application, args.application_id)
        if application is None:
            print(f"No application found with id {args.application_id}", file=sys.stderr)
            sys.exit(1)
        job = session.get(Job, application.job_id)

        payload = ApplicationPayload(
            source_url=job.source_url,
            full_name="",  # fill in from config/master_profile.json before running
            email="",
            phone="",
            cover_letter_text=application.cover_letter_draft,
        )
        ats_type = job.ats_type.value if hasattr(job.ats_type, "value") else job.ats_type

    if not settings.auto_submit_for(ats_type):
        print(
            f"AUTO_SUBMIT is off for {ats_type} — a browser window will open "
            "pre-filled for you to review and submit manually."
        )

    runner = PlaywrightRunner()
    status = runner.run(ats_type, payload)
    print(f"Result: {status}")


def main() -> None:
    parser = argparse.ArgumentParser(description="job-agent CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db").set_defaults(func=cmd_init_db)
    subparsers.add_parser("scan").set_defaults(func=cmd_scan)
    subparsers.add_parser("check-status").set_defaults(func=cmd_check_status)

    run_app_parser = subparsers.add_parser("run-application")
    run_app_parser.add_argument("application_id")
    run_app_parser.set_defaults(func=cmd_run_application)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
