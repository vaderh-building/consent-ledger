#!/usr/bin/env python3
"""Populate the database with a clearly-synthetic-but-structurally-realistic shape.

Names like "Synthetic Major A" are intentional: this is a portfolio demo and
shouldn't suggest endorsement by or affiliation with any real label. The artist
mix exercises the consent-policy axes the gate cares about (allow/deny per
use_type, weight caps, partial coverage of use_types).

Run directly: `python scripts/seed.py`. The script is idempotent — if a name
is already present it's left alone.
"""

from __future__ import annotations

from app.db import SessionLocal, init_db
from app.domain.enums import UseType
from app.domain.schemas import ConsentPolicyEntryIn
from app.services import (
    artists as artists_svc,
)
from app.services import (
    consent_policies as policy_svc,
)
from app.services import (
    rights_holders as rh_svc,
)
from app.services.signing import ensure_keypair

RIGHTS_HOLDERS: list[str] = [
    "Synthetic Major A",
    "Synthetic Major B",
    "Synthetic Major C",
    "Synthetic Indie Aggregator",
    "Synthetic Publisher Collective",
]

# (rights_holder_name, artist_name, policy_entries, notes)
ARTISTS: list[tuple[str, str, list[ConsentPolicyEntryIn], str]] = [
    (
        "Synthetic Major A",
        "Aurelia Vance",
        [
            ConsentPolicyEntryIn(use_type=UseType.STYLE_CONDITIONING, allowed=True),
            ConsentPolicyEntryIn(use_type=UseType.VOICE_CLONING, allowed=True),
            ConsentPolicyEntryIn(use_type=UseType.STEM_USE, allowed=True),
            ConsentPolicyEntryIn(use_type=UseType.FULL_TRACK_REFERENCE, allowed=True),
            ConsentPolicyEntryIn(use_type=UseType.LYRICAL_REFERENCE, allowed=True),
        ],
        "fully permissive — agent has signed off on the lab pilot",
    ),
    (
        "Synthetic Major A",
        "Cyril Bone",
        [
            ConsentPolicyEntryIn(use_type=UseType.STYLE_CONDITIONING, allowed=True),
            ConsentPolicyEntryIn(use_type=UseType.VOICE_CLONING, allowed=False),
            ConsentPolicyEntryIn(use_type=UseType.STEM_USE, allowed=True, max_weight=0.5),
            ConsentPolicyEntryIn(use_type=UseType.LYRICAL_REFERENCE, allowed=True),
        ],
        "style ok; voice cloning explicitly off the table",
    ),
    (
        "Synthetic Major B",
        "Mira Halsey-Quinn",
        [
            ConsentPolicyEntryIn(use_type=UseType.STYLE_CONDITIONING, allowed=False),
            ConsentPolicyEntryIn(use_type=UseType.VOICE_CLONING, allowed=False),
            ConsentPolicyEntryIn(use_type=UseType.STEM_USE, allowed=False),
            ConsentPolicyEntryIn(use_type=UseType.FULL_TRACK_REFERENCE, allowed=False),
            ConsentPolicyEntryIn(use_type=UseType.LYRICAL_REFERENCE, allowed=False),
        ],
        "no AI use of any kind, period",
    ),
    (
        "Synthetic Major B",
        "Idris Wen",
        [
            ConsentPolicyEntryIn(use_type=UseType.STEM_USE, allowed=True, max_weight=0.4),
            ConsentPolicyEntryIn(use_type=UseType.STYLE_CONDITIONING, allowed=False),
            ConsentPolicyEntryIn(use_type=UseType.VOICE_CLONING, allowed=False),
            ConsentPolicyEntryIn(use_type=UseType.FULL_TRACK_REFERENCE, allowed=False),
            ConsentPolicyEntryIn(use_type=UseType.LYRICAL_REFERENCE, allowed=False),
        ],
        "stem use only, capped",
    ),
    (
        "Synthetic Major C",
        "Joaquin Sera",
        [
            ConsentPolicyEntryIn(use_type=UseType.STYLE_CONDITIONING, allowed=True, max_weight=0.6),
            ConsentPolicyEntryIn(use_type=UseType.VOICE_CLONING, allowed=True, max_weight=0.3),
            ConsentPolicyEntryIn(use_type=UseType.STEM_USE, allowed=True),
            ConsentPolicyEntryIn(use_type=UseType.FULL_TRACK_REFERENCE, allowed=False),
            ConsentPolicyEntryIn(use_type=UseType.LYRICAL_REFERENCE, allowed=True),
        ],
        "broadly permissive but with weight caps",
    ),
    (
        "Synthetic Major C",
        "Petra Lo",
        [
            ConsentPolicyEntryIn(use_type=UseType.STYLE_CONDITIONING, allowed=True, max_weight=0.3),
            ConsentPolicyEntryIn(use_type=UseType.VOICE_CLONING, allowed=False),
            ConsentPolicyEntryIn(use_type=UseType.STEM_USE, allowed=False),
            ConsentPolicyEntryIn(use_type=UseType.FULL_TRACK_REFERENCE, allowed=False),
            ConsentPolicyEntryIn(use_type=UseType.LYRICAL_REFERENCE, allowed=True),
        ],
        "style with hard cap; lyrical reference ok",
    ),
    (
        "Synthetic Indie Aggregator",
        "Nico Reeve",
        [
            ConsentPolicyEntryIn(use_type=UseType.STYLE_CONDITIONING, allowed=True),
            ConsentPolicyEntryIn(use_type=UseType.VOICE_CLONING, allowed=True, max_weight=0.5),
            ConsentPolicyEntryIn(use_type=UseType.STEM_USE, allowed=True),
            ConsentPolicyEntryIn(use_type=UseType.FULL_TRACK_REFERENCE, allowed=True, max_weight=0.4),
            ConsentPolicyEntryIn(use_type=UseType.LYRICAL_REFERENCE, allowed=True),
        ],
        "permissive but with caps",
    ),
    (
        "Synthetic Indie Aggregator",
        "Sasha Vox",
        [
            ConsentPolicyEntryIn(use_type=UseType.LYRICAL_REFERENCE, allowed=True),
            ConsentPolicyEntryIn(use_type=UseType.STYLE_CONDITIONING, allowed=False),
            ConsentPolicyEntryIn(use_type=UseType.VOICE_CLONING, allowed=False),
            ConsentPolicyEntryIn(use_type=UseType.STEM_USE, allowed=False),
            ConsentPolicyEntryIn(use_type=UseType.FULL_TRACK_REFERENCE, allowed=False),
        ],
        "lyrical reference only — songwriter-first stance",
    ),
    (
        "Synthetic Publisher Collective",
        "Rhea Calder",
        [
            ConsentPolicyEntryIn(use_type=UseType.STYLE_CONDITIONING, allowed=True),
            ConsentPolicyEntryIn(use_type=UseType.FULL_TRACK_REFERENCE, allowed=True, max_weight=0.5),
            ConsentPolicyEntryIn(use_type=UseType.VOICE_CLONING, allowed=False),
            ConsentPolicyEntryIn(use_type=UseType.STEM_USE, allowed=False),
            ConsentPolicyEntryIn(use_type=UseType.LYRICAL_REFERENCE, allowed=True),
        ],
        "compositional uses ok; vocal/stem off-limits",
    ),
    (
        "Synthetic Publisher Collective",
        "Oren Hask",
        [
            ConsentPolicyEntryIn(use_type=UseType.STYLE_CONDITIONING, allowed=True),
            ConsentPolicyEntryIn(use_type=UseType.VOICE_CLONING, allowed=False),
            ConsentPolicyEntryIn(use_type=UseType.STEM_USE, allowed=False),
            ConsentPolicyEntryIn(use_type=UseType.FULL_TRACK_REFERENCE, allowed=False),
            ConsentPolicyEntryIn(use_type=UseType.LYRICAL_REFERENCE, allowed=False),
        ],
        "style only",
    ),
]


def seed() -> None:
    init_db()
    ensure_keypair()
    session = SessionLocal()
    try:
        rh_ids: dict[str, int] = {}
        for name in RIGHTS_HOLDERS:
            existing = next(
                (rh for rh in rh_svc.list_rights_holders(session) if rh.name == name),
                None,
            )
            if existing:
                rh_ids[name] = existing.id
                print(f"  rights holder exists: {name} (#{existing.id})")
                continue
            rh = rh_svc.create_rights_holder(session, name=name)
            rh_ids[name] = rh.id
            print(f"+ rights holder: {name} (#{rh.id})")

        existing_artist_names = {a.name for a in artists_svc.list_artists(session)}
        for rh_name, artist_name, entries, notes in ARTISTS:
            if artist_name in existing_artist_names:
                print(f"  artist exists: {artist_name}")
                continue
            a = artists_svc.create_artist(
                session, rights_holder_id=rh_ids[rh_name], name=artist_name
            )
            policy_svc.create_consent_policy(
                session, artist_id=a.id, entries=entries, notes=notes
            )
            allowed = ", ".join(e.use_type for e in entries if e.allowed) or "<nothing>"
            print(f"+ artist: {artist_name:<20s} ({rh_name})  allows: {allowed}")

    finally:
        session.close()
    print()
    print("seed complete.")


if __name__ == "__main__":
    seed()
