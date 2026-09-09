"""Environment/config loading and feature flags.

Every ATS auto-submission path must check settings.AUTO_SUBMIT_APPLICATIONS
(and its per-ATS overrides) before Playwright is allowed to click a final
submit button. Default is always off.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Feature flags ---
    AUTO_SUBMIT_APPLICATIONS: bool = False
    # Per-ATS overrides let you opt in gradually (e.g. Greenhouse only).
    AUTO_SUBMIT_GREENHOUSE: bool = False
    AUTO_SUBMIT_LEVER: bool = False
    AUTO_SUBMIT_WORKDAY: bool = False

    # --- Database ---
    DB_BACKEND: str = "sqlite"  # "sqlite" | "supabase"
    SQLITE_PATH: str = "database/job_agent.db"
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""
    SUPABASE_DB_URL: str = ""

    # --- LLM ---
    LLM_PROVIDER: str = "openrouter"  # "openrouter" | "huggingface"
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_MODEL: str = "meta-llama/llama-3.1-8b-instruct:free"
    HF_API_TOKEN: str = ""
    HF_MODEL: str = ""

    # --- Email (Resend API) ---
    RESEND_API_KEY: str = ""
    EMAIL_FROM: str = ""
    EMAIL_TO: str = ""

    # --- Webhook exposure ---
    NGROK_AUTHTOKEN: str = ""
    PUBLIC_BASE_URL: str = "http://localhost:8000"

    # --- Approval token signing ---
    APPROVAL_TOKEN_SECRET: str = ""
    APPROVAL_TOKEN_TTL_SECONDS: int = 259200  # 72h

    # --- Scraper etiquette ---
    SCRAPER_MIN_DELAY_SECONDS: float = 3.0
    SCRAPER_USER_AGENT: str = "job-agent/0.1 (personal use)"

    def auto_submit_for(self, ats: str) -> bool:
        """Resolve whether auto-submit is enabled for a specific ATS.

        Both the global flag AND the per-ATS flag must be true — this keeps
        opting in to one site from silently enabling all of them.
        """
        per_ats = {
            "greenhouse": self.AUTO_SUBMIT_GREENHOUSE,
            "lever": self.AUTO_SUBMIT_LEVER,
            "workday": self.AUTO_SUBMIT_WORKDAY,
        }
        return self.AUTO_SUBMIT_APPLICATIONS and per_ats.get(ats.lower(), False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
