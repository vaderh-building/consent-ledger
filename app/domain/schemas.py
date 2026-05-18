"""Pydantic v2 request/response schemas.

These are the contract for the HTTP layer. Domain functions accept Pydantic-shaped
inputs or pure dataclasses where they don't touch I/O; ORM models stay inside
services/.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import AuthorizationDecision, UseType

# ---------- Rights holders / artists ----------


class RightsHolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class RightsHolderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime


class ArtistCreate(BaseModel):
    rights_holder_id: int
    name: str = Field(min_length=1, max_length=200)


class ArtistOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    rights_holder_id: int
    name: str
    created_at: datetime


# ---------- Consent policy ----------


class ConsentPolicyEntryIn(BaseModel):
    use_type: UseType
    allowed: bool
    max_weight: float | None = Field(default=None, ge=0.0, le=1.0)


class ConsentPolicyEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    use_type: UseType
    allowed: bool
    max_weight: float | None


class ConsentPolicyCreate(BaseModel):
    artist_id: int
    notes: str | None = Field(default=None, max_length=500)
    entries: list[ConsentPolicyEntryIn] = Field(min_length=1)


class ConsentPolicyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    artist_id: int
    version: int
    notes: str | None
    created_at: datetime
    entries: list[ConsentPolicyEntryOut]


# ---------- Authorization gate ----------


class ProposedInput(BaseModel):
    artist_id: int
    use_type: UseType
    requested_weight: float = Field(ge=0.0, le=1.0)


class AuthorizationRequest(BaseModel):
    initiating_artist_id: int
    inputs: list[ProposedInput] = Field(min_length=1)


class ResolvedInput(BaseModel):
    artist_id: int
    rights_holder_id: int
    use_type: UseType
    requested_weight: float
    granted_weight: float
    allowed: bool
    consent_policy_version: int | None
    reason: str


class AuthorizationResponse(BaseModel):
    decision: AuthorizationDecision
    initiating_artist_id: int
    resolved_inputs: list[ResolvedInput]


# ---------- Provenance / consumption / settlement (forward-declared for later commits) ----------


class GenerationCreate(BaseModel):
    initiating_artist_id: int
    inputs: list[ProposedInput] = Field(min_length=1)


class RecordedInput(BaseModel):
    artist_id: int
    rights_holder_id: int
    use_type: UseType
    consent_policy_version: int
    weight: float


class GenerationOut(BaseModel):
    index: int
    timestamp: datetime
    initiating_artist_id: int
    inputs: list[RecordedInput]
    prev_hash: str
    entry_hash: str
    signature: str


class ProvenanceHead(BaseModel):
    head_hash: str
    entry_count: int


class VerifyResponse(BaseModel):
    ok: bool
    entry_count: int
    first_tampered_index: int | None = None
    message: str | None = None


class ConsumptionEventCreate(BaseModel):
    generation_index: int
    units: int = Field(ge=1)
    period: str = Field(min_length=1, max_length=40)


class ConsumptionEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    generation_index: int
    units: int
    period: str
    created_at: datetime


class RightsHolderPayout(BaseModel):
    rights_holder_id: int
    rights_holder_name: str
    amount: float


class ArtistPayout(BaseModel):
    artist_id: int
    artist_name: str
    rights_holder_id: int
    amount: float


class SettlementReport(BaseModel):
    period: str
    pool_per_unit: float
    initiating_artist_share: float
    total_units: int
    total_pool: float
    per_rights_holder: list[RightsHolderPayout]
    per_initiating_artist: list[ArtistPayout]
    formula: str


class GenerationCitation(BaseModel):
    generation_index: int
    timestamp: datetime
    initiating_artist_id: int
    consent_policy_version: int
    use_type: UseType
    weight: float
    units_consumed: int
    rights_holder_share_of_generation: float
    amount_for_this_rights_holder: float
    prev_hash: str
    entry_hash: str
    signature: str
    canonical_entry_body: str  # canonical JSON used to recompute entry_hash


class RightsHolderStatement(BaseModel):
    rights_holder_id: int
    rights_holder_name: str
    period: str
    total_amount: float
    pool_per_unit: float
    initiating_artist_share: float
    service_public_key_pem: str
    citations: list[GenerationCitation]
    head_hash: str
    entry_count: int
