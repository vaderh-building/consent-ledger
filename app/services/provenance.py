"""Provenance log service: append-only, hash-chained, Ed25519-signed.

POST /generations runs the gate, rejects DENY, drops stripped inputs on PARTIAL,
and atomically appends one entry whose hash commits to the prior head. The tail
of the log can be re-verified at any time without trusting the operator: replay
the chain against the stored canonical body and re-check each Ed25519 signature.

Why we persist `canonical_body` verbatim: SQLite has no timezone-aware datetime
storage, so round-tripping a `datetime` through the DB can drop tzinfo and change
the ISO string a verifier would rebuild. The bytes we signed are the source of
truth and must travel with the row.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.domain.enums import AuthorizationDecision
from app.domain.models import ProvenanceEntry, ProvenanceEntryInput
from app.domain.provenance import GENESIS_PREV_HASH, build_entry_body, canonical_json
from app.domain.schemas import (
    AuthorizationRequest,
    GenerationCreate,
    GenerationOut,
    ProvenanceHead,
    RecordedInput,
    VerifyResponse,
)
from app.services.authorization import authorize
from app.services.signing import sign, verify


class ProvenanceError(Exception):
    pass


def _head(session: Session) -> tuple[str, int]:
    last = session.execute(
        select(ProvenanceEntry).order_by(desc(ProvenanceEntry.index)).limit(1)
    ).scalar_one_or_none()
    if last is None:
        return GENESIS_PREV_HASH, 0
    return last.entry_hash, last.index + 1


def get_head(session: Session) -> ProvenanceHead:
    head_hash, next_index = _head(session)
    return ProvenanceHead(head_hash=head_hash, entry_count=next_index)


def record_generation(session: Session, payload: GenerationCreate) -> GenerationOut:
    decision = authorize(
        session,
        AuthorizationRequest(
            initiating_artist_id=payload.initiating_artist_id,
            inputs=payload.inputs,
        ),
    )

    if decision.decision == AuthorizationDecision.DENY:
        reasons = "; ".join(r.reason for r in decision.resolved_inputs)
        raise ProvenanceError(f"generation denied by consent gate: {reasons}")

    granted = [r for r in decision.resolved_inputs if r.allowed]

    prev_hash, next_index = _head(session)
    ts = datetime.now(UTC)
    ts_iso = ts.isoformat()

    recorded = [
        {
            "artist_id": r.artist_id,
            "rights_holder_id": r.rights_holder_id,
            "use_type": str(r.use_type),
            "consent_policy_version": r.consent_policy_version,
            "weight": r.granted_weight,
        }
        for r in granted
    ]

    body = build_entry_body(
        index=next_index,
        timestamp_iso=ts_iso,
        initiating_artist_id=payload.initiating_artist_id,
        inputs=recorded,
    )
    canonical = canonical_json(body)
    entry_hash = hashlib.sha256(
        prev_hash.encode("ascii") + canonical.encode("utf-8")
    ).hexdigest()
    signature = sign(entry_hash.encode("ascii")).hex()

    entry = ProvenanceEntry(
        index=next_index,
        timestamp=ts,
        initiating_artist_id=payload.initiating_artist_id,
        prev_hash=prev_hash,
        entry_hash=entry_hash,
        signature=signature,
        canonical_body=canonical,
    )
    entry.inputs = [
        ProvenanceEntryInput(
            position=i,
            artist_id=item["artist_id"],
            rights_holder_id=item["rights_holder_id"],
            use_type=item["use_type"],
            consent_policy_version=item["consent_policy_version"],
            weight=item["weight"],
        )
        for i, item in enumerate(body["inputs"])
    ]
    session.add(entry)
    session.commit()
    session.refresh(entry)

    return GenerationOut(
        index=entry.index,
        timestamp=entry.timestamp,
        initiating_artist_id=entry.initiating_artist_id,
        inputs=[
            RecordedInput(
                artist_id=item["artist_id"],
                rights_holder_id=item["rights_holder_id"],
                use_type=item["use_type"],
                consent_policy_version=item["consent_policy_version"],
                weight=item["weight"],
            )
            for item in body["inputs"]
        ],
        prev_hash=entry.prev_hash,
        entry_hash=entry.entry_hash,
        signature=entry.signature,
    )


def _fail(entries_count: int, idx: int, msg: str) -> VerifyResponse:
    return VerifyResponse(
        ok=False, entry_count=entries_count, first_tampered_index=idx, message=msg
    )


def verify_chain(session: Session) -> VerifyResponse:
    """Replay the chain top-to-bottom and re-check every signature.

    The stored canonical_body is the source of truth for the hash. We additionally
    cross-check the structured input rows against the parsed canonical body so
    that mutating a row (e.g. changing a weight) trips a mismatch at exactly the
    index that was tampered with.
    """
    entries = list(
        session.execute(select(ProvenanceEntry).order_by(ProvenanceEntry.index)).scalars()
    )
    total = len(entries)

    expected_prev = GENESIS_PREV_HASH
    for entry in entries:
        # 1. prev_hash chains to previous entry_hash
        if entry.prev_hash != expected_prev:
            return _fail(total, entry.index, "prev_hash does not chain to previous entry_hash")

        # 2. entry_hash = sha256(prev_hash || canonical_body)
        recomputed = hashlib.sha256(
            entry.prev_hash.encode("ascii") + entry.canonical_body.encode("utf-8")
        ).hexdigest()
        if recomputed != entry.entry_hash:
            return _fail(total, entry.index, "entry_hash mismatch")

        # 3. Ed25519 signature is over entry_hash
        if not verify(bytes.fromhex(entry.signature), entry.entry_hash.encode("ascii")):
            return _fail(total, entry.index, "signature does not verify")

        # 4. Structured input rows match the canonical body (so DB mutations are caught)
        try:
            parsed = json.loads(entry.canonical_body)
        except json.JSONDecodeError:
            return _fail(total, entry.index, "canonical_body is not valid JSON")

        if parsed.get("index") != entry.index:
            return _fail(total, entry.index, "canonical body index does not match row index")
        if parsed.get("initiating_artist_id") != entry.initiating_artist_id:
            return _fail(total, entry.index, "canonical body initiating_artist_id mismatch")

        expected_inputs = parsed.get("inputs", [])
        rebuilt_inputs = [
            {
                "artist_id": ri.artist_id,
                "rights_holder_id": ri.rights_holder_id,
                "use_type": str(ri.use_type),
                "consent_policy_version": ri.consent_policy_version,
                "weight": ri.weight,
            }
            for ri in entry.inputs
        ]
        # Sort both the same way to compare semantically.
        key = lambda r: (r["artist_id"], r["use_type"])  # noqa: E731
        if sorted(rebuilt_inputs, key=key) != sorted(expected_inputs, key=key):
            return _fail(
                total,
                entry.index,
                "structured input rows do not match stored canonical body",
            )

        expected_prev = entry.entry_hash

    return VerifyResponse(ok=True, entry_count=total)


def count(session: Session) -> int:
    return int(session.execute(select(func.count()).select_from(ProvenanceEntry)).scalar_one())
