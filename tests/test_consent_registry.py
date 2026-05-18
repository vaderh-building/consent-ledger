"""Consent registry: append-only versioning + historical queries."""

from __future__ import annotations


def _seed_rh_artist(client) -> tuple[int, int]:
    rh = client.post("/rights-holders", json={"name": "RH1"}).json()
    a = client.post(
        "/artists", json={"rights_holder_id": rh["id"], "name": "A1"}
    ).json()
    return rh["id"], a["id"]


def test_create_rights_holder_and_artist(client):
    rh = client.post("/rights-holders", json={"name": "Acme"}).json()
    assert rh["id"] == 1 and rh["name"] == "Acme"

    a = client.post("/artists", json={"rights_holder_id": rh["id"], "name": "Beta"})
    assert a.status_code == 201
    assert a.json()["rights_holder_id"] == rh["id"]


def test_artist_create_requires_existing_rights_holder(client):
    r = client.post("/artists", json={"rights_holder_id": 999, "name": "Ghost"})
    assert r.status_code == 404


def test_rights_holder_name_must_be_unique(client):
    client.post("/rights-holders", json={"name": "OnlyOne"})
    r = client.post("/rights-holders", json={"name": "OnlyOne"})
    assert r.status_code == 409


def test_consent_policy_versions_increment_per_artist(client):
    _, aid = _seed_rh_artist(client)

    v1 = client.post(
        "/consent-policies",
        json={
            "artist_id": aid,
            "entries": [{"use_type": "STYLE_CONDITIONING", "allowed": True}],
        },
    ).json()
    v2 = client.post(
        "/consent-policies",
        json={
            "artist_id": aid,
            "entries": [{"use_type": "STYLE_CONDITIONING", "allowed": False}],
        },
    ).json()
    assert v1["version"] == 1
    assert v2["version"] == 2


def test_consent_policy_historical_query(client):
    _, aid = _seed_rh_artist(client)
    client.post(
        "/consent-policies",
        json={
            "artist_id": aid,
            "entries": [
                {"use_type": "STYLE_CONDITIONING", "allowed": True, "max_weight": 0.5}
            ],
        },
    )
    client.post(
        "/consent-policies",
        json={
            "artist_id": aid,
            "entries": [{"use_type": "STYLE_CONDITIONING", "allowed": False}],
        },
    )

    latest = client.get(f"/artists/{aid}/consent-policy").json()
    v1 = client.get(f"/artists/{aid}/consent-policy?version=1").json()
    assert latest["version"] == 2
    assert latest["entries"][0]["allowed"] is False
    assert v1["version"] == 1
    assert v1["entries"][0]["allowed"] is True
    assert v1["entries"][0]["max_weight"] == 0.5


def test_consent_policy_duplicate_use_type_rejected(client):
    _, aid = _seed_rh_artist(client)
    r = client.post(
        "/consent-policies",
        json={
            "artist_id": aid,
            "entries": [
                {"use_type": "STYLE_CONDITIONING", "allowed": True},
                {"use_type": "STYLE_CONDITIONING", "allowed": False},
            ],
        },
    )
    assert r.status_code == 400


def test_consent_policy_missing_artist_rejected(client):
    r = client.post(
        "/consent-policies",
        json={
            "artist_id": 999,
            "entries": [{"use_type": "STYLE_CONDITIONING", "allowed": True}],
        },
    )
    assert r.status_code == 400


def test_missing_policy_returns_404(client):
    _, aid = _seed_rh_artist(client)
    r = client.get(f"/artists/{aid}/consent-policy")
    assert r.status_code == 404
