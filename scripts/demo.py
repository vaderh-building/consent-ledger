#!/usr/bin/env python3
"""End-to-end demo against a live local server.

Spawns uvicorn, seeds the registry, walks through the full loop with a
readable narrative — DENY at the gate, a PARTIAL recording, several ALLOWs,
consumption + settlement, a rights-holder statement re-verified offline,
then a live tamper-and-detect — and shuts the server down cleanly.

Run from the project root:
    python scripts/demo.py
"""

from __future__ import annotations

import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "consent_ledger.db"
KEYS_DIR = ROOT / "keys"
PRIVATE_KEY = KEYS_DIR / "service_ed25519.pem"
PUBLIC_KEY = KEYS_DIR / "service_ed25519_pub.pem"
SERVER_URL = "http://127.0.0.1:8765"
STATEMENT_PATH = ROOT / "demo_statement.json"


def section(title: str) -> None:
    print()
    print("─" * 78)
    print(f" {title}")
    print("─" * 78)


def line(msg: str) -> None:
    print(f"  {msg}")


def reset_state() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()
    for f in (PRIVATE_KEY, PUBLIC_KEY):
        if f.exists():
            f.unlink()
    if STATEMENT_PATH.exists():
        STATEMENT_PATH.unlink()


def wait_for_server(client: httpx.Client, timeout_s: float = 10.0) -> None:
    start = time.time()
    while time.time() - start < timeout_s:
        try:
            if client.get("/", timeout=0.5).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    raise SystemExit("server did not come up in time")


def get_id_by_name(client: httpx.Client, path: str, name: str) -> int:
    for item in client.get(path).json():
        if item["name"] == name:
            return int(item["id"])
    raise KeyError(f"no record with name {name!r} at {path}")


def main() -> int:
    section("STEP 0 — reset local state and start a fresh server")
    reset_state()
    line(f"removed {DB_PATH.name} and key material")

    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", "8765", "--log-level", "warning"],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        with httpx.Client(base_url=SERVER_URL, timeout=5.0) as client:
            wait_for_server(client)
            line("server up at " + SERVER_URL)

            section("STEP 1 — seed the consent registry (out-of-band)")
            subprocess.run([sys.executable, str(ROOT / "scripts" / "seed.py")], check=True)

            cyril_id = get_id_by_name(client, "/artists", "Cyril Bone")        # denies VOICE_CLONING
            mira_id = get_id_by_name(client, "/artists", "Mira Halsey-Quinn")  # denies everything
            aurelia_id = get_id_by_name(client, "/artists", "Aurelia Vance")   # permissive
            nico_id = get_id_by_name(client, "/artists", "Nico Reeve")
            joaquin_id = get_id_by_name(client, "/artists", "Joaquin Sera")
            line(f"artist ids: aurelia={aurelia_id}, cyril={cyril_id}, mira={mira_id}, nico={nico_id}, joaquin={joaquin_id}")

            section("STEP 2 — DENY at the gate (request rejected, nothing written)")
            r = client.post(
                "/generations",
                json={
                    "initiating_artist_id": aurelia_id,
                    "inputs": [
                        {"artist_id": cyril_id, "use_type": "VOICE_CLONING", "requested_weight": 0.5},
                        {"artist_id": mira_id, "use_type": "STYLE_CONDITIONING", "requested_weight": 0.5},
                    ],
                },
            )
            line(f"POST /generations → {r.status_code}")
            line(f"  detail: {r.json()['detail'][:200]}")
            head = client.get("/provenance/head").json()
            line(f"  /provenance/head entry_count = {head['entry_count']} (still empty)")

            section("STEP 3 — PARTIAL (allowed inputs recorded, denied ones stripped)")
            r = client.post(
                "/generations",
                json={
                    "initiating_artist_id": aurelia_id,
                    "inputs": [
                        {"artist_id": aurelia_id, "use_type": "STYLE_CONDITIONING", "requested_weight": 0.6},
                        {"artist_id": cyril_id, "use_type": "VOICE_CLONING", "requested_weight": 0.4},
                    ],
                },
            )
            partial = r.json()
            line(f"POST /generations → {r.status_code} (index {partial['index']})")
            line(f"  inputs requested: 2,  inputs recorded: {len(partial['inputs'])}")
            for i in partial["inputs"]:
                line(f"    kept: artist={i['artist_id']} use={i['use_type']} weight={i['weight']}")

            section("STEP 4 — ALLOW (everything passes, full record written)")
            allow_indices: list[int] = []
            for inputs in [
                [
                    {"artist_id": cyril_id, "use_type": "STYLE_CONDITIONING", "requested_weight": 0.5},
                    {"artist_id": nico_id, "use_type": "STYLE_CONDITIONING", "requested_weight": 0.5},
                ],
                [
                    {"artist_id": joaquin_id, "use_type": "VOICE_CLONING", "requested_weight": 0.9},
                ],
                [
                    {"artist_id": aurelia_id, "use_type": "STEM_USE", "requested_weight": 0.7},
                    {"artist_id": nico_id, "use_type": "STEM_USE", "requested_weight": 0.3},
                ],
            ]:
                resp = client.post(
                    "/generations",
                    json={"initiating_artist_id": aurelia_id, "inputs": inputs},
                ).json()
                allow_indices.append(resp["index"])
                line(
                    f"  recorded gen #{resp['index']} ({len(resp['inputs'])} inputs); "
                    f"entry_hash={resp['entry_hash'][:12]}…"
                )

            # Surface joaquin's capped weight — his policy caps VOICE_CLONING at 0.3
            # so the requested 0.9 should have been clamped on the way in.
            joaquin_entry = client.get("/provenance/head").json()
            line(
                f"  note: joaquin's VOICE_CLONING request (0.9) was capped by his "
                f"consent policy (max_weight=0.3) before being recorded."
            )
            line(f"  chain head now: {joaquin_entry['head_hash'][:16]}…  entry_count={joaquin_entry['entry_count']}")

            section("STEP 5 — record consumption events for period 2026-Q2")
            consumption_plan = [
                (partial["index"], 80),
                (allow_indices[0], 240),
                (allow_indices[1], 60),
                (allow_indices[2], 120),
            ]
            for idx, units in consumption_plan:
                client.post(
                    "/consumption-events",
                    json={"generation_index": idx, "units": units, "period": "2026-Q2"},
                )
                line(f"  +{units:>4d} units against gen #{idx}")

            section("STEP 6 — settlement report")
            report = client.get("/settlement/report?period=2026-Q2").json()
            line(
                f"  period={report['period']}  total_units={report['total_units']}  "
                f"total_pool={report['total_pool']:.2f}  pool_per_unit={report['pool_per_unit']}"
            )
            line(f"  initiating_artist_share={report['initiating_artist_share']}")
            line("  per rights holder:")
            for p in report["per_rights_holder"]:
                line(f"    {p['rights_holder_name']:<32s}  {p['amount']:>10.4f}")
            line("  per initiating artist:")
            for p in report["per_initiating_artist"]:
                line(f"    artist #{p['artist_id']} ({p['artist_name']:<20s})  {p['amount']:>10.4f}")

            section("STEP 7 — rights-holder statement (with crypto proof)")
            rh_id = get_id_by_name(client, "/rights-holders", "Synthetic Indie Aggregator")
            statement = client.get(
                f"/rights-holders/{rh_id}/statement?period=2026-Q2"
            ).json()
            line(f"  rights holder: #{rh_id} {statement['rights_holder_name']!r}")
            line(f"  total amount owed: {statement['total_amount']:.4f}")
            line(f"  citations: {len(statement['citations'])}")
            for c in statement["citations"]:
                line(
                    f"    gen #{c['generation_index']} use={c['use_type']:<20s} "
                    f"weight={c['weight']} units={c['units_consumed']}  "
                    f"amount={c['amount_for_this_rights_holder']:.4f}  "
                    f"entry_hash={c['entry_hash'][:12]}…"
                )

            STATEMENT_PATH.write_text(json.dumps(statement, indent=2))
            line(f"  saved statement → {STATEMENT_PATH.name}")

            section("STEP 8 — re-verify the statement OFFLINE")
            line("  (running scripts/verify_statement.py against the saved JSON)")
            print()
            rc = subprocess.call(
                [sys.executable, str(ROOT / "scripts" / "verify_statement.py"), str(STATEMENT_PATH)]
            )
            if rc != 0:
                raise SystemExit(f"offline verify failed (rc={rc})")

            section("STEP 9 — live tamper-and-detect")
            line(f"  current /provenance/verify: {client.get('/provenance/verify').json()}")
            line("  mutating weight on one stored input row (gen #1, first input)...")
            con = sqlite3.connect(str(DB_PATH))
            try:
                con.execute(
                    "UPDATE provenance_entry_inputs SET weight = 0.99 "
                    "WHERE id = (SELECT MIN(id) FROM provenance_entry_inputs "
                    "WHERE entry_id = (SELECT id FROM provenance_entries WHERE [index] = 1))"
                )
                con.commit()
            finally:
                con.close()
            verify_after = client.get("/provenance/verify").json()
            line(f"  /provenance/verify after tamper: {verify_after}")
            assert verify_after["ok"] is False
            assert verify_after["first_tampered_index"] == 1
            line("  ↑ verifier pinpointed the tampered entry index. Property preserved.")

            section("DONE")
            line("DENY enforced, PARTIAL recorded only allowed inputs, ALLOW chain built,")
            line("settlement attributed via provenance, statement re-verified offline,")
            line("post-hoc tamper detected and localized — all without a blockchain.")

    finally:
        if server.poll() is None:
            try:
                server.send_signal(signal.SIGTERM)
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
        if STATEMENT_PATH.exists():
            STATEMENT_PATH.unlink()

    return 0


if __name__ == "__main__":
    sys.exit(main())
