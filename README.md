# Consent–Attribution–Settlement Ledger

A backend service that makes artist consent, attribution, and compensation
mechanically enforceable at the moment of AI music generation — without a
blockchain.

Spotify's Artist-First AI Music lab has signed deals with major rights holders
and made four public promises: license-first, artist opt-in over *if and how*
their work is used, fair compensation + transparent credit, and artist–fan
connection. The middle two only become real when there is infrastructure that
enforces them — a system that refuses unauthorized inputs at the gate, records
exactly what was used and under whose consent at the moment of generation, and
lets every rights holder verify their statement themselves. This is that
infrastructure, stripped to its smallest defensible form.

There is no audio ML in this project. The hard problem here is data systems.

## What's inside

- **Granular consent registry** — rights holders, artists, and per-use-type
  consent policies that are versioned and append-only. Use-types are
  `STYLE_CONDITIONING`, `VOICE_CLONING`, `STEM_USE`, `FULL_TRACK_REFERENCE`,
  `LYRICAL_REFERENCE`. Superseding a policy mints version N+1; old versions
  remain queryable forever.
- **Pre-generation authorization gate** — `POST /authorize` resolves a proposed
  generation against each cited artist's latest policy and returns
  `ALLOW`/`PARTIAL`/`DENY` with a per-input reason. Fails closed: missing
  artist, missing policy, missing entry, or explicit deny all reject.
- **Provenance log** — `POST /generations` re-runs the gate, refuses `DENY`,
  drops stripped inputs on `PARTIAL`, and appends one Ed25519-signed,
  hash-chained entry committing to the prior head. `GET /provenance/verify`
  replays the chain and pinpoints any tampered index.
- **Settlement / metering** — `POST /consumption-events` records unit-scale
  plays against a known generation; `GET /settlement/report?period=…` joins
  consumption back through the provenance log and splits each event's pool
  between the initiating artist and the recorded rights holders by weight.
- **Self-verification statements** — `GET /rights-holders/{id}/statement?period=…`
  returns every citing generation with its `prev_hash`, `entry_hash`,
  signature, and the verbatim canonical JSON we hashed, plus the service
  public-key PEM. `scripts/verify_statement.py` re-checks all of it offline.

## Why not a blockchain

The full argument is in [DESIGN.md](./DESIGN.md#why-not-a-blockchain). Short
version: the hard problem here is the *oracle problem* — deciding which
copyrighted inputs fed a generation under which consent version happens
off-chain, and a chain can only immutably record the output of that decision.
The counterparties are ~5 named, contractually-bound institutions, so
trustlessness among anonymous adversaries (the property a public chain is
uniquely good at) is not the missing ingredient. The signed, hash-chained
append-only log plus inclusion proofs delivers tamper-evidence and
independent verifiability without taking on the trade-offs.

## Run it

```bash
make install          # one-time: venv + dependencies
make test             # 25 tests, 95% coverage on app/domain + app/services
make demo             # end-to-end live narrative on a local server
```

`make demo` resets the local DB, spawns uvicorn, seeds the registry, walks
the full loop (DENY → PARTIAL → ALLOW → consumption → settlement → statement
→ offline verify → tamper-and-detect), then cleans up.

To explore by hand:

```bash
make seed             # populate the DB with synthetic data
make run              # uvicorn on :8000
open http://localhost:8000/docs
```

## The loop, walked through

```
   POST /rights-holders ──┐
   POST /artists ─────────┼─► registry (5 RHs, 10 artists)
   POST /consent-policies ┘     versioned per-artist, per-use-type

   POST /authorize ──────────► ALLOW | PARTIAL | DENY  (no writes)

   POST /generations ────────► re-run gate; reject DENY; drop stripped
                                inputs on PARTIAL; append signed entry
                                committing to prior head_hash
        │
        ▼
   POST /consumption-events ─► record unit-scale plays vs. that gen
        │
        ▼
   GET /settlement/report?period=…
        ─► per-RH and per-initiating-artist payout + formula

   GET /rights-holders/{id}/statement?period=…
        ─► every citing generation with its crypto proof
        ─► verifiable offline with scripts/verify_statement.py

   GET /provenance/verify ───► replay chain; pinpoint first tampered index
```

## Architecture

Clean layered Python:

- `app/domain/` — pure models, enums, Pydantic schemas, hash-chain helpers.
  No I/O.
- `app/services/` — orchestration. SQLAlchemy session work, signing, gate
  resolution, chain append, settlement math.
- `app/api/` — thin FastAPI routers. Business logic stays out.

SQLite is the database (single file, foreign keys on). Signing key is
generated on first run and lives in `keys/` (gitignored). Nothing external.

## Repo layout

```
app/
  domain/      enums, ORM models, schemas, hash helpers
  services/    rights_holders, artists, consent_policies, authorization,
               provenance, consumption, settlement, statements, signing
  api/         one router file per resource
tests/         pytest suite (25 cases, 95% coverage on domain+services)
scripts/
  seed.py                 idempotent registry fixture loader
  demo.py                 full end-to-end live narrative
  verify_statement.py     offline re-verifier for a saved statement JSON
  export_openapi.py       dump openapi.json to disk
openapi.json              exported OpenAPI spec
DESIGN.md                 architecture + "why not a blockchain"
NARRATIVE.md              one-page first-person framing
```
