"""Rights-holder self-verification statements.

A statement is everything a rights holder needs to independently re-derive what
they're owed for a period, plus the cryptographic material to confirm the citing
generations were actually recorded. Specifically each citation carries the
verbatim `canonical_entry_body` we hashed, the `prev_hash` it linked to, the
`entry_hash` itself, and the Ed25519 `signature` — so a recipient can:

  recomputed_hash = sha256(prev_hash || canonical_entry_body)        ==> entry_hash
  Ed25519.verify(public_key_pem, signature, entry_hash)              ==> True
  re-derived_amount = derive_from(canonical_entry_body, units_consumed, params) ==> amount

…all without trusting us. scripts/verify_statement.py is the canonical
client-side implementation of that procedure.
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import INITIATING_ARTIST_SHARE, SETTLEMENT_POOL_PER_UNIT
from app.domain.models import (
    ConsumptionEvent,
    ProvenanceEntry,
    ProvenanceEntryInput,
    RightsHolder,
)
from app.domain.schemas import GenerationCitation, RightsHolderStatement
from app.services.provenance import get_head
from app.services.signing import public_key_pem


class StatementError(Exception):
    pass


def build_statement(
    session: Session, *, rights_holder_id: int, period: str
) -> RightsHolderStatement:
    rh = session.get(RightsHolder, rights_holder_id)
    if rh is None:
        raise StatementError(f"rights holder {rights_holder_id} not found")

    # 1. Consumption events in the period, summed per generation.
    events = list(
        session.execute(
            select(ConsumptionEvent).where(ConsumptionEvent.period == period)
        ).scalars()
    )
    units_by_gen: dict[int, int] = defaultdict(int)
    for ev in events:
        units_by_gen[ev.generation_index] += ev.units

    if not units_by_gen:
        return RightsHolderStatement(
            rights_holder_id=rh.id,
            rights_holder_name=rh.name,
            period=period,
            total_amount=0.0,
            pool_per_unit=SETTLEMENT_POOL_PER_UNIT,
            initiating_artist_share=INITIATING_ARTIST_SHARE,
            service_public_key_pem=public_key_pem(),
            citations=[],
            head_hash=get_head(session).head_hash,
            entry_count=get_head(session).entry_count,
        )

    # 2. Pull every input row attributed to this RH within those generations.
    contributing_rows = list(
        session.execute(
            select(ProvenanceEntryInput)
            .join(ProvenanceEntry, ProvenanceEntry.id == ProvenanceEntryInput.entry_id)
            .where(
                ProvenanceEntryInput.rights_holder_id == rights_holder_id,
                ProvenanceEntry.index.in_(list(units_by_gen.keys())),
            )
        ).scalars()
    )

    citations: list[GenerationCitation] = []
    total_amount = 0.0
    for row in contributing_rows:
        entry = row.entry
        units_consumed = units_by_gen[entry.index]
        pool = units_consumed * SETTLEMENT_POOL_PER_UNIT
        contributors_share = pool - pool * INITIATING_ARTIST_SHARE
        total_weight = sum(ri.weight for ri in entry.inputs)
        if total_weight <= 0:
            continue
        weight_fraction = row.weight / total_weight
        amount = contributors_share * weight_fraction
        total_amount += amount

        citations.append(
            GenerationCitation(
                generation_index=entry.index,
                timestamp=entry.timestamp,
                initiating_artist_id=entry.initiating_artist_id,
                consent_policy_version=row.consent_policy_version,
                use_type=row.use_type,
                weight=row.weight,
                units_consumed=units_consumed,
                rights_holder_share_of_generation=round(weight_fraction, 6),
                amount_for_this_rights_holder=round(amount, 6),
                prev_hash=entry.prev_hash,
                entry_hash=entry.entry_hash,
                signature=entry.signature,
                canonical_entry_body=entry.canonical_body,
            )
        )

    head = get_head(session)
    return RightsHolderStatement(
        rights_holder_id=rh.id,
        rights_holder_name=rh.name,
        period=period,
        total_amount=round(total_amount, 6),
        pool_per_unit=SETTLEMENT_POOL_PER_UNIT,
        initiating_artist_share=INITIATING_ARTIST_SHARE,
        service_public_key_pem=public_key_pem(),
        citations=sorted(citations, key=lambda c: (c.generation_index, c.use_type)),
        head_hash=head.head_hash,
        entry_count=head.entry_count,
    )
