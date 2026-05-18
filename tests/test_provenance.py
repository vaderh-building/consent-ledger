"""Provenance log: gate enforcement, chain integrity, head."""

from __future__ import annotations


def _setup(client) -> tuple[int, int, int]:
    rh1 = client.post("/rights-holders", json={"name": "RH1"}).json()["id"]
    rh2 = client.post("/rights-holders", json={"name": "RH2"}).json()["id"]
    a1 = client.post("/artists", json={"rights_holder_id": rh1, "name": "Initiator"}).json()["id"]
    a2 = client.post("/artists", json={"rights_holder_id": rh1, "name": "PermissiveA"}).json()["id"]
    a3 = client.post("/artists", json={"rights_holder_id": rh2, "name": "DeniesVoice"}).json()["id"]
    for aid, allow_voice in [(a1, True), (a2, True), (a3, False)]:
        client.post(
            "/consent-policies",
            json={
                "artist_id": aid,
                "entries": [
                    {"use_type": "STYLE_CONDITIONING", "allowed": True},
                    {"use_type": "VOICE_CLONING", "allowed": allow_voice},
                ],
            },
        )
    return a1, a2, a3


def test_deny_at_gate_returns_403_and_does_not_append(client):
    a1, _, a3 = _setup(client)
    before = client.get("/provenance/head").json()
    r = client.post(
        "/generations",
        json={
            "initiating_artist_id": a1,
            "inputs": [
                {"artist_id": a3, "use_type": "VOICE_CLONING", "requested_weight": 0.5},
            ],
        },
    )
    after = client.get("/provenance/head").json()
    assert r.status_code == 403
    assert before == after


def test_partial_records_only_allowed_inputs(client):
    a1, a2, a3 = _setup(client)
    r = client.post(
        "/generations",
        json={
            "initiating_artist_id": a1,
            "inputs": [
                {"artist_id": a2, "use_type": "STYLE_CONDITIONING", "requested_weight": 0.5},
                {"artist_id": a3, "use_type": "VOICE_CLONING", "requested_weight": 0.5},
            ],
        },
    ).json()
    assert len(r["inputs"]) == 1
    assert r["inputs"][0]["artist_id"] == a2


def test_chain_links_and_verifies(client):
    a1, a2, _ = _setup(client)
    indices = []
    for _ in range(3):
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
    assert indices == [0, 1, 2]
    assert client.get("/provenance/verify").json()["ok"] is True
    head = client.get("/provenance/head").json()
    assert head["entry_count"] == 3
