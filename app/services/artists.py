"""Artist service."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import Artist, RightsHolder


class ArtistError(Exception):
    pass


def create_artist(session: Session, *, rights_holder_id: int, name: str) -> Artist:
    rh = session.get(RightsHolder, rights_holder_id)
    if rh is None:
        raise ArtistError(f"rights holder {rights_holder_id} not found")
    artist = Artist(rights_holder_id=rights_holder_id, name=name)
    session.add(artist)
    session.commit()
    session.refresh(artist)
    return artist


def get_artist(session: Session, artist_id: int) -> Artist | None:
    return session.get(Artist, artist_id)


def list_artists(session: Session) -> list[Artist]:
    return list(session.execute(select(Artist).order_by(Artist.id)).scalars())
