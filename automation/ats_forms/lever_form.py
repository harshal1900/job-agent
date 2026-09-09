"""Lever application form filler — stub.

Implement fill()/submit() following automation/ats_forms/greenhouse_form.py
once the Greenhouse pilot (scrapers + this form-fill flow) is validated
end-to-end. Lever's posting apply form is typically at
jobs.lever.co/<company>/<posting-id>/apply.
"""

from __future__ import annotations

from playwright.sync_api import Page


def fill(page: Page, payload) -> None:
    raise NotImplementedError(
        "Lever form-fill is not implemented yet — see "
        "automation/ats_forms/greenhouse_form.py for the reference pattern."
    )


def submit(page: Page) -> None:
    raise NotImplementedError("Lever form-fill is not implemented yet.")
