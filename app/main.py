"""FastAPI application entrypoint.

Routers are wired in here; all business logic lives in services/ and domain/.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import init_db


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


app = FastAPI(
    title="Consent–Attribution–Settlement Ledger",
    description=(
        "Tamper-evident infrastructure that makes artist consent, attribution, and "
        "compensation mechanically enforceable at the moment of AI generation."
    ),
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/", tags=["meta"])
def root() -> dict[str, str]:
    return {"service": "consent-ledger", "docs": "/docs"}
