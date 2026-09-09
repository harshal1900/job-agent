"""Local CLI entrypoint — run pieces of the pipeline by hand without the
FastAPI server, e.g. for the first end-to-end pilot run (PRD build step 9).

Usage:
    python manage.py init-db
    python manage.py scan
    python manage.py retry-pending
    python manage.py check-status
    python manage.py run-application <application_id>
    python manage.py serve [--scan-now]

`retry-pending` re-attempts scoring/tailoring for jobs already in the DB
that never got a real score or failed tailoring last time (e.g. after
hitting an LLM rate limit or a malformed-response bug) — without
re-scraping. `scan` only ever looks at brand-new postings; it silently
skips any source_url already in the DB, success or failure, so it will
NOT retry anything on its own.

`run-application` is a separate CLI step (not a FastAPI request handler) on
purpose — see automation/playwright_runner.py: in manual mode it leaves a
real browser window open for you to review and click submit, which needs a
foreground process, not an async request/response cycle.

`serve` boots the actual FastAPI app in-process (so the ngrok tunnel opened
in api/main.py's lifespan, if ENABLE_NGROK_TUNNEL=true, updates the same
settings singleton everything else reads) and keeps it running so /respond
links work when clicked. `--scan-now` runs one scan cycle right after
startup instead of waiting for the 6h APScheduler interval — needed because
a plain `python manage.py scan` runs in a separate process and would build
approval links against the *unmodified* PUBLIC_BASE_URL from .env, not the
live tunnel URL.
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


def cmd_retry_pending(_args) -> None:
    from database.db import init_db
    from api.scheduler import retry_pending_jobs

    init_db()
    result = retry_pending_jobs()
    print(
        f"Retry complete: {result['scored_now']} jobs newly scored, "
        f"{result['tailored_now']} jobs newly tailored + emailed."
    )


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


def cmd_serve(args) -> None:
    import signal
    import threading
    import time

    import uvicorn

    from api.main import app
    from api.scheduler import scan_job
    from config.settings import get_settings

    settings = get_settings()

    config = uvicorn.Config(app, host="0.0.0.0", port=settings.APP_PORT, log_level="info")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    while not server.started:
        time.sleep(0.1)

    print(f"Server up on http://localhost:{settings.APP_PORT}")
    if settings.ENABLE_NGROK_TUNNEL:
        print(f"Public tunnel: {settings.PUBLIC_BASE_URL}")
    else:
        print("ENABLE_NGROK_TUNNEL is off — approval links use PUBLIC_BASE_URL from .env as-is.")

    if args.scan_now:
        print("Running one scan cycle now...")
        scan_job()
        print("Scan cycle complete.")

    print("Serving — Ctrl+C (or SIGTERM) to stop; this also closes the ngrok tunnel.")

    # server.run() only watches for signals on the thread it's actually
    # running on. Since we launched it on a background thread, catch
    # SIGINT/SIGTERM here on the main thread instead so `kill <pid>` (not
    # just Ctrl+C) still triggers a graceful shutdown — and with it, the
    # api/main.py lifespan's stop_tunnel() cleanup — rather than leaving an
    # orphaned ngrok process behind.
    stop_requested = threading.Event()

    def _handle_signal(signum, _frame):
        stop_requested.set()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    while thread.is_alive() and not stop_requested.is_set():
        time.sleep(0.5)

    if stop_requested.is_set():
        server.should_exit = True
        thread.join()


def main() -> None:
    parser = argparse.ArgumentParser(description="job-agent CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db").set_defaults(func=cmd_init_db)
    subparsers.add_parser("scan").set_defaults(func=cmd_scan)
    subparsers.add_parser("retry-pending").set_defaults(func=cmd_retry_pending)
    subparsers.add_parser("check-status").set_defaults(func=cmd_check_status)

    run_app_parser = subparsers.add_parser("run-application")
    run_app_parser.add_argument("application_id")
    run_app_parser.set_defaults(func=cmd_run_application)

    serve_parser = subparsers.add_parser("serve")
    serve_parser.add_argument("--scan-now", action="store_true")
    serve_parser.set_defaults(func=cmd_serve)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
