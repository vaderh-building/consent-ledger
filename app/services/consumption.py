"""Consumption-event service.

Records a unit-scale consumption (stand-in for a stream/play) against a known
provenance entry. We refuse to record consumption for a generation index that
isn't in the provenance log — otherwise the attribution joins later would be
silently incomplete.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import ConsumptionEvent, ProvenanceEntry


class ConsumptionError(Exception):
    pass


def record_consumption(
    session: Session, *, generation_index: int, units: int, period: str
) -> ConsumptionEvent:
    exists = session.execute(
        select(ProvenanceEntry.id).where(ProvenanceEntry.index == generation_index)
    ).scalar_one_or_none()
    if exists is None:
        raise ConsumptionError(f"no provenance entry at index {generation_index}")

    event = ConsumptionEvent(generation_index=generation_index, units=units, period=period)
    session.add(event)
    session.commit()
    session.refresh(event)
    return event
