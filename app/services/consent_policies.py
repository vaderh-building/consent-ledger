"""Consent-policy service: append-only, versioned per artist."""

from __future__ import annotations

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.domain.models import Artist, ConsentPolicy, ConsentPolicyEntry
from app.domain.schemas import ConsentPolicyEntryIn


class ConsentPolicyError(Exception):
    pass


def _next_version_for_artist(session: Session, artist_id: int) -> int:
    current_max = session.execute(
        select(func.max(ConsentPolicy.version)).where(ConsentPolicy.artist_id == artist_id)
    ).scalar_one_or_none()
    return (current_max or 0) + 1


def create_consent_policy(
    session: Session,
    *,
    artist_id: int,
    entries: list[ConsentPolicyEntryIn],
    notes: str | None,
) -> ConsentPolicy:
    artist = session.get(Artist, artist_id)
    if artist is None:
        raise ConsentPolicyError(f"artist {artist_id} not found")

    seen: set[str] = set()
    for e in entries:
        if e.use_type in seen:
            raise ConsentPolicyError(f"duplicate use_type {e.use_type} in policy entries")
        seen.add(e.use_type)
        if e.allowed and e.max_weight is None:
            # default cap is the full requested weight; absence ≠ no cap
            pass

    policy = ConsentPolicy(
        artist_id=artist_id,
        version=_next_version_for_artist(session, artist_id),
        notes=notes,
    )
    policy.entries = [
        ConsentPolicyEntry(
            use_type=e.use_type,
            allowed=e.allowed,
            max_weight=e.max_weight,
        )
        for e in entries
    ]
    session.add(policy)
    session.commit()
    session.refresh(policy)
    return policy


def get_latest_policy(session: Session, artist_id: int) -> ConsentPolicy | None:
    return session.execute(
        select(ConsentPolicy)
        .where(ConsentPolicy.artist_id == artist_id)
        .order_by(desc(ConsentPolicy.version))
        .limit(1)
    ).scalar_one_or_none()


def get_policy_version(
    session: Session, artist_id: int, version: int
) -> ConsentPolicy | None:
    return session.execute(
        select(ConsentPolicy)
        .where(ConsentPolicy.artist_id == artist_id, ConsentPolicy.version == version)
    ).scalar_one_or_none()
