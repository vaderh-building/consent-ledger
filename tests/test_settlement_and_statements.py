"""Settlement math + statement self-verification (both online and offline)."""

from __future__ import annotations

import hashlib
import json

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def _seed_for_settlement(client) -> tuple[int, int, int, int, int]:
    rh1 = client.post("/rights-holders", json={"name": "RH1"}).json()["id"]
    rh2 = client.post("/rights-holders", json={"name": "RH2"}).json()["id"]
    a_init = client.post(
        "/artists", json={"rights_holder_id": rh1, "name": "Initiator"}
    ).json()["id"]
    a_a = client.post(
        "/artists", json={"rights_holder_id": rh1, "name": "ContribA"}
    ).json()["id"]
    a_b = client.post(
        "/artists", json={"rights_holder_id": rh2, "name": "ContribB"}
    ).json()["id"]
    for aid in [a_init, a_a, a_b]:
        client.post(
            "/consent-policies",
            json={
                "artist_id": aid,
                "entries": [
                    {"use_type": "STYLE_CONDITIONING", "allowed": True},
                    {"use_type": "VOICE_CLONING", "allowed": True},
                ],
            },
        )
    return rh1, rh2, a_init, a_a, a_b


def test_settlement_math(client):
    rh1, rh2, a_init, a_a, a_b = _seed_for_settlement(client)

    g0 = client.post(
        "/generations",
        json={
            "initiating_artist_id": a_init,
            "inputs": [
                {"artist_id": a_a, "use_type": "STYLE_CONDITIONING", "requested_weight": 0.5},
                {"artist_id": a_b, "use_type": "STYLE_CONDITIONING", "requested_weight": 0.5},
            ],
        },
    ).json()
    g1 = client.post(
        "/generations",
        json={
            "initiating_artist_id": a_init,
            "inputs": [
                {"artist_id": a_b, "use_type": "VOICE_CLONING", "requested_weight": 1.0},
            ],
        },
    ).json()
    client.post(
        "/consumption-events",
        json={"generation_index": g0["index"], "units": 100, "period": "P"},
    )
    client.post(
        "/consumption-events",
        json={"generation_index": g1["index"], "units": 50, "period": "P"},
    )

    report = client.get("/settlement/report?period=P").json()

    # Pool = 100 + 50 = 150. Initiator share 0.30 -> 45. Contributors share -> 105.
    # G0 contrib share = 70, split 50/50 between RH1 and RH2 -> 35 each.
    # G1 contrib share = 35, all to RH2.
    # => RH1: 35, RH2: 35 + 35 = 70. Initiator: 30 + 15 = 45.
    rh_amounts = {p["rights_holder_id"]: p["amount"] for p in report["per_rights_holder"]}
    assert rh_amounts[rh1] == 35.0
    assert rh_amounts[rh2] == 70.0
    assert report["per_initiating_artist"][0]["amount"] == 45.0
    assert report["total_pool"] == 150.0


def test_unknown_generation_index_rejected(client):
    r = client.post(
        "/consumption-events",
        json={"generation_index": 999, "units": 1, "period": "P"},
    )
    assert r.status_code == 404


def test_statement_includes_proof_and_verifies_offline(client):
    rh1, rh2, a_init, a_a, a_b = _seed_for_settlement(client)
    g0 = client.post(
        "/generations",
        json={
            "initiating_artist_id": a_init,
            "inputs": [
                {"artist_id": a_a, "use_type": "STYLE_CONDITIONING", "requested_weight": 0.5},
                {"artist_id": a_b, "use_type": "STYLE_CONDITIONING", "requested_weight": 0.5},
            ],
        },
    ).json()
    client.post(
        "/consumption-events",
        json={"generation_index": g0["index"], "units": 200, "period": "P"},
    )

    stmt = client.get(f"/rights-holders/{rh2}/statement?period=P").json()
    assert stmt["rights_holder_id"] == rh2
    assert len(stmt["citations"]) == 1
    c0 = stmt["citations"][0]

    # Re-derive entry_hash from prev_hash + canonical_entry_body
    recomputed = hashlib.sha256(
        c0["prev_hash"].encode("ascii") + c0["canonical_entry_body"].encode("utf-8")
    ).hexdigest()
    assert recomputed == c0["entry_hash"]

    # Verify Ed25519 signature against embedded public key
    pub = serialization.load_pem_public_key(stmt["service_public_key_pem"].encode("ascii"))
    assert isinstance(pub, Ed25519PublicKey)
    pub.verify(bytes.fromhex(c0["signature"]), c0["entry_hash"].encode("ascii"))

    # Re-derive amount
    body = json.loads(c0["canonical_entry_body"])
    total_weight = sum(i["weight"] for i in body["inputs"])
    expected = (
        c0["units_consumed"]
        * stmt["pool_per_unit"]
        * (1 - stmt["initiating_artist_share"])
        * (c0["weight"] / total_weight)
    )
    assert abs(expected - c0["amount_for_this_rights_holder"]) < 1e-6
    assert abs(stmt["total_amount"] - expected) < 1e-6


def test_statement_for_unknown_rights_holder_is_404(client):
    r = client.get("/rights-holders/999/statement?period=P")
    assert r.status_code == 404
