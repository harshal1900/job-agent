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
from database.db import init_db

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    scheduler = start_scheduler()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="Job Agent", lifespan=lifespan)
app.include_router(approval_router)


@app.get("/health")
def health():
    return {"ok": True}
