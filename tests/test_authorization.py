"""Authorization gate: ALLOW / PARTIAL / DENY and weight capping."""

from __future__ import annotations


def _make_artist(client, rh_name: str, artist_name: str, entries: list[dict]) -> int:
    rh = client.post("/rights-holders", json={"name": rh_name}).json()
    a = client.post(
        "/artists", json={"rights_holder_id": rh["id"], "name": artist_name}
    ).json()
    client.post(
        "/consent-policies", json={"artist_id": a["id"], "entries": entries}
    )
    return a["id"]


def test_allow_all_inputs(client):
    a1 = _make_artist(
        client,
        "RH1",
        "Permissive",
        [{"use_type": "STYLE_CONDITIONING", "allowed": True}],
    )
    a2 = _make_artist(
        client,
        "RH2",
        "Permissive2",
        [{"use_type": "STYLE_CONDITIONING", "allowed": True}],
    )
    r = client.post(
        "/authorize",
        json={
            "initiating_artist_id": a1,
            "inputs": [
                {"artist_id": a1, "use_type": "STYLE_CONDITIONING", "requested_weight": 0.5},
                {"artist_id": a2, "use_type": "STYLE_CONDITIONING", "requested_weight": 0.5},
            ],
        },
    ).json()
    assert r["decision"] == "ALLOW"
    assert all(i["allowed"] for i in r["resolved_inputs"])


def test_partial_strips_denied_inputs(client):
    a1 = _make_artist(
        client,
        "RH1",
        "Permissive",
        [{"use_type": "STYLE_CONDITIONING", "allowed": True}],
    )
    a2 = _make_artist(
        client,
        "RH2",
        "DeniesVoice",
        [
            {"use_type": "STYLE_CONDITIONING", "allowed": True},
            {"use_type": "VOICE_CLONING", "allowed": False},
        ],
    )
    r = client.post(
        "/authorize",
        json={
            "initiating_artist_id": a1,
            "inputs": [
                {"artist_id": a1, "use_type": "STYLE_CONDITIONING", "requested_weight": 0.5},
                {"artist_id": a2, "use_type": "VOICE_CLONING", "requested_weight": 0.5},
            ],
        },
    ).json()
    assert r["decision"] == "PARTIAL"
    allowed = [i for i in r["resolved_inputs"] if i["allowed"]]
    denied = [i for i in r["resolved_inputs"] if not i["allowed"]]
    assert len(allowed) == 1 and len(denied) == 1
    assert "denies VOICE_CLONING" in denied[0]["reason"]


def test_deny_when_no_input_authorized(client):
    a1 = _make_artist(
        client,
        "RH1",
        "DeniesAll",
        [{"use_type": "VOICE_CLONING", "allowed": False}],
    )
    r = client.post(
        "/authorize",
        json={
            "initiating_artist_id": a1,
            "inputs": [
                {"artist_id": a1, "use_type": "VOICE_CLONING", "requested_weight": 0.5},
                {"artist_id": 999, "use_type": "STYLE_CONDITIONING", "requested_weight": 0.5},
            ],
        },
    ).json()
    assert r["decision"] == "DENY"
    reasons = [i["reason"] for i in r["resolved_inputs"]]
    assert any("not found" in x for x in reasons)
    assert any("denies VOICE_CLONING" in x for x in reasons)


def test_weight_cap_clamps_but_still_allows(client):
    a1 = _make_artist(
        client,
        "RH1",
        "Capped",
        [{"use_type": "STYLE_CONDITIONING", "allowed": True, "max_weight": 0.4}],
    )
    r = client.post(
        "/authorize",
        json={
            "initiating_artist_id": a1,
            "inputs": [
                {"artist_id": a1, "use_type": "STYLE_CONDITIONING", "requested_weight": 0.9},
            ],
        },
    ).json()
    assert r["decision"] == "ALLOW"
    assert r["resolved_inputs"][0]["granted_weight"] == 0.4
    assert "capped" in r["resolved_inputs"][0]["reason"]


def test_use_type_not_in_policy_is_denied(client):
    a1 = _make_artist(
        client,
        "RH1",
        "PartialPolicy",
        [{"use_type": "STYLE_CONDITIONING", "allowed": True}],
    )
    r = client.post(
        "/authorize",
        json={
            "initiating_artist_id": a1,
            "inputs": [
                {"artist_id": a1, "use_type": "STEM_USE", "requested_weight": 0.5},
            ],
        },
    ).json()
    assert r["decision"] == "DENY"
    assert "does not cover use type" in r["resolved_inputs"][0]["reason"]
