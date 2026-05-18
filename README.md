# Consent–Attribution–Settlement Ledger

**Start here.** Open [`index.html`](./index.html) in your browser. Double-clicking
the file is enough, there is no server and no build. The page is a markets
argument about why the per-stream royalty for AI-generated music collapses
under the current logic, with a live chart and sliders so you can try to
slider the collapse away and confirm you cannot. The chart is the first thing
you see; the written argument is immediately below it.

The service in this repository is the layer the page argues for. At the moment
a generation is about to happen, the service asks three yes-or-no questions
and commits the answer to an append-only signed log, so that a downstream
auditor can verify what was decided without trusting the operator. The three
questions are whether the source material is licensed, whether the source
artist's consent policy on record allows this specific use of their work, and
whether the resulting payment to the source is recorded in a form that the
source artist can re-derive on their own machine. The signed binary output of
those three checks is what the page calls the **stamp**. A stamped track is
monetizable. An unstamped track is slop.

Spotify's Artist-First AI Music lab has signed deals with major rights holders
and made four public promises, license-first, artist opt-in over *if and how*
their work is used, fair compensation and transparent credit, and artist–fan
connection. The middle two only become real when there is infrastructure that
enforces them at the moment of generation. This is that infrastructure,
stripped to its smallest defensible form, paired with the markets argument
that says what such a layer is actually paying for in a saturated-supply world.

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

Integrity comes from a signed, append-only hash-chained log; every statement
carries an inclusion proof that any rights holder can verify offline.

## The chart and the model

The page at [`index.html`](./index.html) is the markets argument. Its
two-line chart is computed live in the browser, and the same arithmetic
lives as a documented Python reference at [`model/compensation.py`](./model/compensation.py)
with its own test file at [`tests/test_model.py`](./tests/test_model.py).
The load-bearing assertion in those tests is that even at the most
source-favorable slider corner (slow growth, blend width of 1, and a 50
percent source take under the current model), the red per-stream curve
still falls below 25 percent of its starting value by month 12. The
collapse is structural, not a function of pessimistic inputs.

## Run it

```bash
make install          # one-time: venv + dependencies
make test             # 40 tests across the service + the chart's model
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
index.html                self-contained markets argument + live chart
model/                    Python reference for the chart's two-line model
  compensation.py
app/
  domain/      enums, ORM models, schemas, hash helpers
  services/    rights_holders, artists, consent_policies, authorization,
               provenance, consumption, settlement, statements, signing
  api/         one router file per resource
tests/         pytest suite (40 cases total — service + chart model)
scripts/
  seed.py                 idempotent registry fixture loader
  demo.py                 full end-to-end live narrative
  verify_statement.py     offline re-verifier for a saved statement JSON
  export_openapi.py       dump openapi.json to disk
openapi.json              exported OpenAPI spec
DESIGN.md                 architecture + integrity and verifiability
NARRATIVE.md              one-page first-person framing
```
