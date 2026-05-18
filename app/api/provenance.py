"""Provenance HTTP routes: append, head, verify."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_session
from app.domain.schemas import (
    GenerationCreate,
    GenerationOut,
    ProvenanceHead,
    VerifyResponse,
)
from app.services import provenance as svc

router = APIRouter(tags=["provenance"])


@router.post(
    "/generations", response_model=GenerationOut, status_code=status.HTTP_201_CREATED
)
def post_generation(
    payload: GenerationCreate, session: Session = Depends(get_session)
) -> GenerationOut:
    try:
        return svc.record_generation(session, payload)
    except svc.ProvenanceError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.get("/provenance/head", response_model=ProvenanceHead)
def get_head(session: Session = Depends(get_session)) -> ProvenanceHead:
    return svc.get_head(session)


@router.get("/provenance/verify", response_model=VerifyResponse)
def get_verify(session: Session = Depends(get_session)) -> VerifyResponse:
    return svc.verify_chain(session)
