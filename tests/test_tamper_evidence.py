"""Tamper-evidence: every kind of mutation gets localized to its index.

This is the test that the spec calls out as mandatory. We seed a chain, mutate
one entry in three different ways (structured row, canonical body, signature),
and assert /provenance/verify identifies the right index each time.
"""

from __future__ import annotations


def _seed_chain(client, n: int = 3) -> list[int]:
    rh = client.post("/rights-holders", json={"name": "RH"}).json()["id"]
    a1 = client.post("/artists", json={"rights_holder_id": rh, "name": "A1"}).json()["id"]
    a2 = client.post("/artists", json={"rights_holder_id": rh, "name": "A2"}).json()["id"]
    for aid in [a1, a2]:
        client.post(
            "/consent-policies",
            json={
                "artist_id": aid,
                "entries": [{"use_type": "STYLE_CONDITIONING", "allowed": True}],
            },
        )
    indices = []
    for _ in range(n):
        r = client.post(
            "/generations",
            json={
                "initiating_artist_id": a1,
                "inputs": [
                    {"artist_id": a2, "use_type": "STYLE_CONDITIONING", "requested_weight": 0.5},
                ],
            },
        ).json()
        indices.append(r["index"])
    return indices


def test_clean_chain_verifies(client):
    _seed_chain(client, n=3)
    r = client.get("/provenance/verify").json()
    assert r["ok"] is True
    assert r["first_tampered_index"] is None


def test_tampering_with_input_row_is_localized(client, session):
    from app.domain.models import ProvenanceEntryInput

    _seed_chain(client, n=3)
    target_idx = 1
    rows = list(
        session.execute(
            __import__("sqlalchemy")
            .select(ProvenanceEntryInput)
            .join(ProvenanceEntryInput.entry)
            .where(ProvenanceEntryInput.entry.has(index=target_idx))
        ).scalars()
    )
    assert rows, "expected at least one input row on the target entry"
    rows[0].weight = 0.99
    session.commit()

    r = client.get("/provenance/verify").json()
    assert r["ok"] is False
    assert r["first_tampered_index"] == target_idx
    assert "structured input rows" in r["message"]


def test_tampering_with_canonical_body_is_localized(client, session):
    from app.domain.models import ProvenanceEntry

    _seed_chain(client, n=3)
    target_idx = 2
    entry = session.execute(
        __import__("sqlalchemy")
        .select(ProvenanceEntry)
        .where(ProvenanceEntry.index == target_idx)
    ).scalar_one()
    entry.canonical_body = '{"tampered":true}'
    session.commit()

    r = client.get("/provenance/verify").json()
    assert r["ok"] is False
    assert r["first_tampered_index"] == target_idx
    assert r["message"] == "entry_hash mismatch"


def test_tampering_with_signature_is_localized(client, session):
    from app.domain.models import ProvenanceEntry

    _seed_chain(client, n=3)
    target_idx = 0
    entry = session.execute(
        __import__("sqlalchemy")
        .select(ProvenanceEntry)
        .where(ProvenanceEntry.index == target_idx)
    ).scalar_one()
    sig = list(bytes.fromhex(entry.signature))
    sig[0] ^= 0x01
    entry.signature = bytes(sig).hex()
    session.commit()

    r = client.get("/provenance/verify").json()
    assert r["ok"] is False
    assert r["first_tampered_index"] == target_idx
    assert r["message"] == "signature does not verify"


def test_tampering_with_prev_hash_breaks_chain(client, session):
    from app.domain.models import ProvenanceEntry

    _seed_chain(client, n=3)
    entry = session.execute(
        __import__("sqlalchemy")
        .select(ProvenanceEntry)
        .where(ProvenanceEntry.index == 1)
    ).scalar_one()
    entry.prev_hash = "0" * 64
    session.commit()

    r = client.get("/provenance/verify").json()
    assert r["ok"] is False
    assert r["first_tampered_index"] == 1
