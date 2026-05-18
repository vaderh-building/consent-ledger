"""GET /rights-holders/{id}/statement?period=…

Returned independently from the rights-holders router so its concerns (audits,
settlement) stay separate from the registry CRUD.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db import get_session
from app.domain.schemas import RightsHolderStatement
from app.services import statements as svc

router = APIRouter(tags=["statements"])


@router.get(
    "/rights-holders/{rights_holder_id}/statement",
    response_model=RightsHolderStatement,
)
def get_statement(
    rights_holder_id: int,
    period: str = Query(min_length=1, max_length=40),
    session: Session = Depends(get_session),
) -> RightsHolderStatement:
    try:
        return svc.build_statement(
            session, rights_holder_id=rights_holder_id, period=period
        )
    except svc.StatementError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
