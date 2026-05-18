"""POST /authorize — pure decision endpoint.

This endpoint never writes. It exists so a client can probe whether a generation
*would* be authorized, separately from actually recording it. POST /generations
re-runs the same logic before writing to the provenance log.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_session
from app.domain.schemas import AuthorizationRequest, AuthorizationResponse
from app.services.authorization import authorize

router = APIRouter(tags=["authorization"])


@router.post("/authorize", response_model=AuthorizationResponse)
def post_authorize(
    payload: AuthorizationRequest, session: Session = Depends(get_session)
) -> AuthorizationResponse:
    return authorize(session, payload)
