"""Rights-holder HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_session
from app.domain.schemas import RightsHolderCreate, RightsHolderOut
from app.services import rights_holders as svc

router = APIRouter(prefix="/rights-holders", tags=["rights-holders"])


@router.post("", response_model=RightsHolderOut, status_code=status.HTTP_201_CREATED)
def create(payload: RightsHolderCreate, session: Session = Depends(get_session)) -> RightsHolderOut:
    try:
        rh = svc.create_rights_holder(session, name=payload.name)
    except svc.RightsHolderError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return RightsHolderOut.model_validate(rh)


@router.get("", response_model=list[RightsHolderOut])
def list_all(session: Session = Depends(get_session)) -> list[RightsHolderOut]:
    return [RightsHolderOut.model_validate(rh) for rh in svc.list_rights_holders(session)]


@router.get("/{rights_holder_id}", response_model=RightsHolderOut)
def get_one(rights_holder_id: int, session: Session = Depends(get_session)) -> RightsHolderOut:
    rh = svc.get_rights_holder(session, rights_holder_id)
    if rh is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="rights holder not found")
    return RightsHolderOut.model_validate(rh)
