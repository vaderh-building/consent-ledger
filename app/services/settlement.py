"""Settlement aggregation.

For each consumption event in the period:
  pool                = units * SETTLEMENT_POOL_PER_UNIT
  initiating_share    = pool * INITIATING_ARTIST_SHARE          → initiating artist
  contributors_share  = pool - initiating_share                 → rights holders
                       (distributed proportional to recorded input weights)

When a generation has zero contributing weight (e.g. all granted_weights were 0),
the contributors share is left unallocated rather than retargeted — surfacing this
honestly in the formula keeps the math auditable.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import INITIATING_ARTIST_SHARE, SETTLEMENT_POOL_PER_UNIT
from app.domain.models import (
    Artist,
    ConsumptionEvent,
    ProvenanceEntry,
    RightsHolder,
)
from app.domain.schemas import (
    ArtistPayout,
    RightsHolderPayout,
    SettlementReport,
)

FORMULA_TEXT: str = (
    "per consumption event: pool = units * pool_per_unit; "
    "initiating_share = pool * initiating_artist_share -> initiating artist; "
    "contributors_share = pool - initiating_share -> recorded rights holders, "
    "distributed proportional to recorded input weights. If a generation has zero "
    "total contributing weight the contributors_share is left unallocated."
)


def _consumption_for_period(session: Session, period: str) -> list[ConsumptionEvent]:
    return list(
        session.execute(
            select(ConsumptionEvent).where(ConsumptionEvent.period == period)
        ).scalars()
    )


def _provenance_by_index(
    session: Session, indices: Iterable[int]
) -> dict[int, ProvenanceEntry]:
    if not indices:
        return {}
    rows = list(
        session.execute(
            select(ProvenanceEntry).where(ProvenanceEntry.index.in_(list(indices)))
        ).scalars()
    )
    return {entry.index: entry for entry in rows}


def build_report(session: Session, period: str) -> SettlementReport:
    events = _consumption_for_period(session, period)
    needed_indices = {e.generation_index for e in events}
    provenance = _provenance_by_index(session, needed_indices)

    per_rh: dict[int, float] = defaultdict(float)
    per_artist: dict[int, tuple[int, float]] = {}  # initiating_artist_id -> (rh_id, total)
    total_units = 0
    total_pool = 0.0

    for event in events:
        entry = provenance.get(event.generation_index)
        if entry is None:
            # we refused to record this in consumption.py, but be defensive
            continue
        total_units += event.units
        pool = event.units * SETTLEMENT_POOL_PER_UNIT
        total_pool += pool
        initiating_share = pool * INITIATING_ARTIST_SHARE
        contributors_share = pool - initiating_share

        existing = per_artist.get(entry.initiating_artist_id)
        if existing is None:
            init_artist = session.get(Artist, entry.initiating_artist_id)
            init_rh_id = init_artist.rights_holder_id if init_artist is not None else -1
            per_artist[entry.initiating_artist_id] = (init_rh_id, initiating_share)
        else:
            rh_id, prior = existing
            per_artist[entry.initiating_artist_id] = (rh_id, prior + initiating_share)

        total_weight = sum(ri.weight for ri in entry.inputs)
        if total_weight <= 0:
            continue
        for ri in entry.inputs:
            share = contributors_share * (ri.weight / total_weight)
            per_rh[ri.rights_holder_id] += share

    rh_name_cache: dict[int, str] = {}
    for rh_id in per_rh:
        rh = session.get(RightsHolder, rh_id)
        rh_name_cache[rh_id] = rh.name if rh is not None else f"unknown-{rh_id}"

    artist_name_cache: dict[int, str] = {}
    for artist_id in per_artist:
        a = session.get(Artist, artist_id)
        artist_name_cache[artist_id] = a.name if a is not None else f"unknown-{artist_id}"

    per_rh_out = [
        RightsHolderPayout(
            rights_holder_id=rh_id,
            rights_holder_name=rh_name_cache[rh_id],
            amount=round(amount, 6),
        )
        for rh_id, amount in sorted(per_rh.items())
    ]
    per_artist_out = [
        ArtistPayout(
            artist_id=artist_id,
            artist_name=artist_name_cache[artist_id],
            rights_holder_id=rh_id,
            amount=round(amount, 6),
        )
        for artist_id, (rh_id, amount) in sorted(per_artist.items())
    ]

    return SettlementReport(
        period=period,
        pool_per_unit=SETTLEMENT_POOL_PER_UNIT,
        initiating_artist_share=INITIATING_ARTIST_SHARE,
        total_units=total_units,
        total_pool=round(total_pool, 6),
        per_rights_holder=per_rh_out,
        per_initiating_artist=per_artist_out,
        formula=FORMULA_TEXT,
    )
