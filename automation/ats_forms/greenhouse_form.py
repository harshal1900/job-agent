"""Greenhouse embedded application form filler.

Field selectors target Greenhouse's standard embedded application form
(#application_form). Individual company boards vary (custom questions,
different required fields), so treat these selectors as a starting point to
verify/adjust during the first pilot run (PRD build step 9), not a
guarantee that every board matches exactly.
"""

from __future__ import annotations

from playwright.sync_api import Page


def fill(page: Page, payload) -> None:
    form = page.locator("#application_form")
    form.wait_for(state="visible", timeout=15000)

    first_name, _, last_name = payload.full_name.partition(" ")
    _fill_if_present(page, "#first_name", first_name)
    _fill_if_present(page, "#last_name", last_name or first_name)
    _fill_if_present(page, "#email", payload.email)
    _fill_if_present(page, "#phone", payload.phone)

    if payload.resume_path:
        resume_input = page.locator("#resume")
        if resume_input.count() > 0:
            resume_input.set_input_files(payload.resume_path)

    cover_letter_field = page.locator("#cover_letter_text, textarea#cover_letter")
    if cover_letter_field.count() > 0:
        cover_letter_field.first.fill(payload.cover_letter_text)


def submit(page: Page) -> None:
    submit_button = page.locator("#submit_app, button[type=submit]")
    submit_button.first.click()


def _fill_if_present(page: Page, selector: str, value: str) -> None:
    if not value:
        return
    field = page.locator(selector)
    if field.count() > 0:
        field.first.fill(value)
