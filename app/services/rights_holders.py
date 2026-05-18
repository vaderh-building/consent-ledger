"""Rights-holder service."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.models import RightsHolder


class RightsHolderError(Exception):
    pass


def create_rights_holder(session: Session, *, name: str) -> RightsHolder:
    rh = RightsHolder(name=name)
    session.add(rh)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise RightsHolderError(f"rights holder name {name!r} already exists") from exc
    session.refresh(rh)
    return rh


def get_rights_holder(session: Session, rights_holder_id: int) -> RightsHolder | None:
    return session.get(RightsHolder, rights_holder_id)


def list_rights_holders(session: Session) -> list[RightsHolder]:
    return list(session.execute(select(RightsHolder).order_by(RightsHolder.id)).scalars())
