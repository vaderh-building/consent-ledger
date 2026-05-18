"""Consent-policy HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_session
from app.domain.schemas import ConsentPolicyCreate, ConsentPolicyOut
from app.services import consent_policies as svc

router = APIRouter(prefix="/consent-policies", tags=["consent-policies"])


@router.post("", response_model=ConsentPolicyOut, status_code=status.HTTP_201_CREATED)
def create(
    payload: ConsentPolicyCreate, session: Session = Depends(get_session)
) -> ConsentPolicyOut:
    try:
        policy = svc.create_consent_policy(
            session,
            artist_id=payload.artist_id,
            entries=payload.entries,
            notes=payload.notes,
        )
    except svc.ConsentPolicyError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ConsentPolicyOut.model_validate(policy)
