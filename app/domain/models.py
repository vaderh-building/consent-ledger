"""SQLAlchemy ORM models.

Schema notes:
- ConsentPolicy is versioned per artist. New policies don't mutate old ones — they
  get the next version number. Old versions remain queryable so we can answer
  "under which policy was this generation authorized?" forever.
- ProvenanceEntry / ConsumptionEvent are added in later commits; this file holds
  the consent-registry tables only at this point in the build.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.domain.enums import UseType


def _utcnow() -> datetime:
    return datetime.now(UTC)


class RightsHolder(Base):
    __tablename__ = "rights_holders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    artists: Mapped[list[Artist]] = relationship(back_populates="rights_holder")


class Artist(Base):
    __tablename__ = "artists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rights_holder_id: Mapped[int] = mapped_column(
        ForeignKey("rights_holders.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    rights_holder: Mapped[RightsHolder] = relationship(back_populates="artists")
    consent_policies: Mapped[list[ConsentPolicy]] = relationship(
        back_populates="artist", order_by="ConsentPolicy.version"
    )


class ConsentPolicy(Base):
    """A versioned, append-only consent declaration for one artist.

    Issuing a new policy creates a row with the next version number; existing
    rows are never updated or deleted. Querying by (artist_id, version) gives
    the historical view we need for audits and statements.
    """

    __tablename__ = "consent_policies"
    __table_args__ = (UniqueConstraint("artist_id", "version", name="uq_policy_artist_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    artist_id: Mapped[int] = mapped_column(
        ForeignKey("artists.id", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    artist: Mapped[Artist] = relationship(back_populates="consent_policies")
    entries: Mapped[list[ConsentPolicyEntry]] = relationship(
        back_populates="policy", cascade="all, delete-orphan"
    )


class ConsentPolicyEntry(Base):
    """Per-use-type allow/deny + optional weight cap inside a policy version.

    Absent rows for a given use_type are interpreted as DENY at resolution time,
    so we fail closed: silence is not consent.
    """

    __tablename__ = "consent_policy_entries"
    __table_args__ = (
        UniqueConstraint("policy_id", "use_type", name="uq_entry_policy_use_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy_id: Mapped[int] = mapped_column(
        ForeignKey("consent_policies.id", ondelete="CASCADE"), nullable=False
    )
    use_type: Mapped[UseType] = mapped_column(String(40), nullable=False)
    allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    max_weight: Mapped[float | None] = mapped_column(Float, nullable=True)

    policy: Mapped[ConsentPolicy] = relationship(back_populates="entries")


class ProvenanceEntry(Base):
    """One immutable row in the signed hash-chained log.

    `canonical_body` is the exact JSON string fed into the hash; we persist it
    verbatim so a verifier never has to reconstruct what we hashed.
    """

    __tablename__ = "provenance_entries"
    __table_args__ = (UniqueConstraint("index", name="uq_provenance_index"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    index: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    initiating_artist_id: Mapped[int] = mapped_column(
        ForeignKey("artists.id", ondelete="RESTRICT"), nullable=False
    )
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    signature: Mapped[str] = mapped_column(String(256), nullable=False)
    canonical_body: Mapped[str] = mapped_column(Text, nullable=False)

    inputs: Mapped[list[ProvenanceEntryInput]] = relationship(
        back_populates="entry",
        cascade="all, delete-orphan",
        order_by="ProvenanceEntryInput.position",
    )


class ProvenanceEntryInput(Base):
    """One resolved input attached to a provenance entry.

    Stored as structured rows (rather than only inside canonical_body) so the
    settlement aggregation can do indexed joins. The canonical body remains the
    source of truth for hash verification — these rows are derived from it.
    """

    __tablename__ = "provenance_entry_inputs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_id: Mapped[int] = mapped_column(
        ForeignKey("provenance_entries.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    artist_id: Mapped[int] = mapped_column(
        ForeignKey("artists.id", ondelete="RESTRICT"), nullable=False
    )
    rights_holder_id: Mapped[int] = mapped_column(
        ForeignKey("rights_holders.id", ondelete="RESTRICT"), nullable=False
    )
    use_type: Mapped[UseType] = mapped_column(String(40), nullable=False)
    consent_policy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False)

    entry: Mapped[ProvenanceEntry] = relationship(back_populates="inputs")
