"""FastAPI app entrypoint.

Run locally with: uvicorn api.main:app --reload
Expose /respond via ngrok only during approval windows (PRD risk #2) — don't
leave the tunnel open permanently.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.routes_approval import router as approval_router
from api.scheduler import start_scheduler
from api.tunnel import start_tunnel, stop_tunnel
from config.settings import get_settings
from database.db import init_db

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    settings = get_settings()

    tunnel_opened = False
    if settings.ENABLE_NGROK_TUNNEL:
        public_url = start_tunnel(settings.APP_PORT)
        tunnel_opened = True
        logger.info("Approval endpoints publicly reachable at: %s/respond/...", public_url)
    else:
        logger.info(
            "ENABLE_NGROK_TUNNEL is off — approval links will use PUBLIC_BASE_URL=%s",
            settings.PUBLIC_BASE_URL,
        )

    scheduler = start_scheduler()
    yield
    scheduler.shutdown(wait=False)
    if tunnel_opened:
        stop_tunnel()


app = FastAPI(title="Job Agent", lifespan=lifespan)
app.include_router(approval_router)


@app.get("/health")
def health():
    return {"ok": True}
