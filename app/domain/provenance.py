"""Pure helpers for the provenance hash chain.

Lives in domain/ on purpose: no SQLAlchemy here, no I/O. The same canonical-JSON +
hash routine is used by the service (when appending) and by scripts/verify_statement.py
(when re-checking offline). If those two implementations ever drifted, verification
would silently break — so there is exactly one of them, and it sits here.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

GENESIS_PREV_HASH: str = "0" * 64


def canonical_json(body: dict[str, Any]) -> str:
    """Deterministic JSON: sorted keys, no whitespace, UTF-8 safe.

    Two callers passing semantically-identical dicts MUST produce byte-identical
    output, otherwise hashes will not match. We sort nested lists of inputs by a
    stable tuple before calling this — see build_entry_body.
    """
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def hash_entry(prev_hash: str, body: dict[str, Any]) -> str:
    payload = prev_hash.encode("ascii") + canonical_json(body).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_entry_body(
    *,
    index: int,
    timestamp_iso: str,
    initiating_artist_id: int,
    inputs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Construct the canonical entry body.

    Inputs are sorted by (artist_id, use_type) so the hash is independent of the
    order in which the client supplied them.
    """
    sorted_inputs = sorted(inputs, key=lambda r: (r["artist_id"], r["use_type"]))
    return {
        "index": index,
        "timestamp": timestamp_iso,
        "initiating_artist_id": initiating_artist_id,
        "inputs": sorted_inputs,
    }
