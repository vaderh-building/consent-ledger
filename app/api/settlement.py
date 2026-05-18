"""GET /settlement/report?period=…"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_session
from app.domain.schemas import SettlementReport
from app.services.settlement import build_report

router = APIRouter(tags=["settlement"])


@router.get("/settlement/report", response_model=SettlementReport)
def get_report(
    period: str = Query(min_length=1, max_length=40),
    session: Session = Depends(get_session),
) -> SettlementReport:
    return build_report(session, period)
