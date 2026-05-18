"""POST /consumption-events."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_session
from app.domain.schemas import ConsumptionEventCreate, ConsumptionEventOut
from app.services import consumption as svc

router = APIRouter(tags=["consumption"])


@router.post(
    "/consumption-events",
    response_model=ConsumptionEventOut,
    status_code=status.HTTP_201_CREATED,
)
def post_event(
    payload: ConsumptionEventCreate, session: Session = Depends(get_session)
) -> ConsumptionEventOut:
    try:
        event = svc.record_consumption(
            session,
            generation_index=payload.generation_index,
            units=payload.units,
            period=payload.period,
        )
    except svc.ConsumptionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ConsumptionEventOut.model_validate(event)
