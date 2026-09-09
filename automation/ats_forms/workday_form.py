"""Workday application form filler — stub.

Workday's apply flow is a multi-step, heavily JS-driven wizard that varies
per tenant (often requires account creation first). Do not implement until
the Greenhouse pilot is validated and there's a concrete Workday tenant to
test against.
"""

from __future__ import annotations

from playwright.sync_api import Page


def fill(page: Page, payload) -> None:
    raise NotImplementedError(
        "Workday form-fill is not implemented yet — see "
        "automation/ats_forms/greenhouse_form.py for the reference pattern."
    )


def submit(page: Page) -> None:
    raise NotImplementedError("Workday form-fill is not implemented yet.")
