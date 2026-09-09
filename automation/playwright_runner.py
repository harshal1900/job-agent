"""Fill (and, only if enabled, submit) an ATS application form via Playwright.

Default behavior (AUTO_SUBMIT_APPLICATIONS=false, or the relevant per-ATS
flag off — see config/settings.py Settings.auto_submit_for): fill out every
field it can, then leave the browser window OPEN at the review step for the
user to check and click submit themselves. Only when auto-submit is enabled
for that specific ATS does this click the final submit button on the user's
behalf.

Callers must only invoke this from a short-lived script/CLI context (not an
awaited FastAPI request handler) when auto_submit is False, since the
browser and Playwright driver are deliberately left running after run()
returns so the window stays open for the user.
"""

from __future__ import annotations

from dataclasses import dataclass

from playwright.sync_api import sync_playwright

from automation.ats_forms import greenhouse_form, lever_form, workday_form
from config.settings import get_settings

_FORM_MODULES = {
    "greenhouse": greenhouse_form,
    "lever": lever_form,
    "workday": workday_form,
}


@dataclass
class ApplicationPayload:
    source_url: str
    full_name: str
    email: str
    phone: str
    cover_letter_text: str
    resume_path: str | None = None


class PlaywrightRunner:
    def __init__(self):
        self.settings = get_settings()

    def run(self, ats_type: str, payload: ApplicationPayload) -> str:
        """Fill the form; submit only if auto-submit is enabled for this ATS.

        Returns "SUBMITTED" or "AWAITING_MANUAL_SUBMIT".
        """
        module = _FORM_MODULES.get(ats_type.lower())
        if module is None:
            raise ValueError(f"No form handler for ATS type: {ats_type!r}")

        auto_submit = self.settings.auto_submit_for(ats_type)

        playwright = sync_playwright().start()
        # Headless only for unattended auto-submit; otherwise show the
        # browser so the user can review before clicking submit themselves.
        browser = playwright.chromium.launch(headless=auto_submit)
        context = browser.new_context()
        page = context.new_page()
        page.goto(payload.source_url, wait_until="domcontentloaded")

        module.fill(page, payload)

        if auto_submit:
            module.submit(page)
            browser.close()
            playwright.stop()
            return "SUBMITTED"

        return "AWAITING_MANUAL_SUBMIT"
