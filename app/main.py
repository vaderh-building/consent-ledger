"""FastAPI application entrypoint.

Routers are wired in here; all business logic lives in services/ and domain/.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import (
    artists,
    authorization,
    consent_policies,
    consumption,
    provenance,
    rights_holders,
    settlement,
)
from app.db import init_db
from app.services.signing import ensure_keypair


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_db()
    ensure_keypair()
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

app.include_router(rights_holders.router)
app.include_router(artists.router)
app.include_router(consent_policies.router)
app.include_router(authorization.router)
app.include_router(provenance.router)
app.include_router(consumption.router)
app.include_router(settlement.router)


@app.get("/", tags=["meta"])
def root() -> dict[str, str]:
    return {"service": "consent-ledger", "docs": "/docs"}
