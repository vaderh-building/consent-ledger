"""Pre-generation authorization gate.

Pure decision logic over (proposed inputs, latest consent policies). Writes
nothing. POST /authorize calls this directly; POST /generations re-runs it
internally before deciding whether to append a provenance entry.

Resolution rules:
  - artist missing                → reject the input ("artist N not found")
  - no policy on file             → reject ("artist N has no consent policy on file")
  - no entry for use_type         → reject ("policy vK does not cover <USE_TYPE>")
  - entry.allowed = False         → reject ("policy vK denies <USE_TYPE>")
  - entry.allowed = True, no cap  → grant requested_weight
  - entry.allowed = True, capped  → grant min(requested_weight, max_weight); flag if reduced

Overall decision:
  - all inputs allowed      → ALLOW
  - some allowed, some not  → PARTIAL
  - none allowed            → DENY
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain.enums import AuthorizationDecision
from app.domain.models import Artist
from app.domain.schemas import (
    AuthorizationRequest,
    AuthorizationResponse,
    ProposedInput,
    ResolvedInput,
)
from app.services.consent_policies import get_latest_policy


def _resolve_one(session: Session, proposed: ProposedInput) -> ResolvedInput:
    artist = session.get(Artist, proposed.artist_id)
    if artist is None:
        return ResolvedInput(
            artist_id=proposed.artist_id,
            rights_holder_id=-1,
            use_type=proposed.use_type,
            requested_weight=proposed.requested_weight,
            granted_weight=0.0,
            allowed=False,
            consent_policy_version=None,
            reason=f"artist {proposed.artist_id} not found",
        )

    policy = get_latest_policy(session, proposed.artist_id)
    if policy is None:
        return ResolvedInput(
            artist_id=proposed.artist_id,
            rights_holder_id=artist.rights_holder_id,
            use_type=proposed.use_type,
            requested_weight=proposed.requested_weight,
            granted_weight=0.0,
            allowed=False,
            consent_policy_version=None,
            reason=f"artist {proposed.artist_id} has no consent policy on file",
        )

    entry = next((e for e in policy.entries if e.use_type == proposed.use_type), None)
    if entry is None:
        return ResolvedInput(
            artist_id=proposed.artist_id,
            rights_holder_id=artist.rights_holder_id,
            use_type=proposed.use_type,
            requested_weight=proposed.requested_weight,
            granted_weight=0.0,
            allowed=False,
            consent_policy_version=policy.version,
            reason=(
                f"consent policy v{policy.version} for artist {proposed.artist_id} "
                f"does not cover use type {proposed.use_type}"
            ),
        )

    if not entry.allowed:
        return ResolvedInput(
            artist_id=proposed.artist_id,
            rights_holder_id=artist.rights_holder_id,
            use_type=proposed.use_type,
            requested_weight=proposed.requested_weight,
            granted_weight=0.0,
            allowed=False,
            consent_policy_version=policy.version,
            reason=(
                f"artist {proposed.artist_id} denies {proposed.use_type} under "
                f"consent policy v{policy.version}"
            ),
        )

    granted = proposed.requested_weight
    capped = False
    if entry.max_weight is not None and granted > entry.max_weight:
        granted = entry.max_weight
        capped = True

    reason = (
        f"allowed under consent policy v{policy.version}"
        + (f"; weight capped to {granted} (requested {proposed.requested_weight})" if capped else "")
    )
    return ResolvedInput(
        artist_id=proposed.artist_id,
        rights_holder_id=artist.rights_holder_id,
        use_type=proposed.use_type,
        requested_weight=proposed.requested_weight,
        granted_weight=granted,
        allowed=True,
        consent_policy_version=policy.version,
        reason=reason,
    )


def authorize(session: Session, request: AuthorizationRequest) -> AuthorizationResponse:
    resolved = [_resolve_one(session, inp) for inp in request.inputs]
    allowed_count = sum(1 for r in resolved if r.allowed)

    if allowed_count == len(resolved):
        decision = AuthorizationDecision.ALLOW
    elif allowed_count == 0:
        decision = AuthorizationDecision.DENY
    else:
        decision = AuthorizationDecision.PARTIAL

    return AuthorizationResponse(
        decision=decision,
        initiating_artist_id=request.initiating_artist_id,
        resolved_inputs=resolved,
    )
