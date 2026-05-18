# Design

## What this service is

A single backend that makes four promises mechanically true at the moment of
AI music generation:

1. **License-first** — every generation event has explicit, recorded
   authorization tied to a specific consent policy version.
2. **Artist opt-in over *if and how*** — consent is granular across use-types
   (style conditioning, voice cloning, stem use, full track reference, lyrical
   reference), versioned, and append-only. Old versions remain queryable.
3. **Fair compensation + transparent credit** — settlement is computed by
   joining consumption events back through the provenance log and splitting a
   per-unit pool by recorded weight. Every rights holder can re-derive their
   own statement offline.
4. **Artist–fan connection** — out of scope as a feature here, but the
   provenance log is the substrate it would sit on, because "this song used
   these artists at these weights" becomes attestable.

## Stack and shape

- Python 3.11+, FastAPI, Pydantic v2, Uvicorn
- SQLAlchemy 2.x + SQLite (single file; no external infra)
- `cryptography` (Ed25519) and `hashlib` (sha256)
- pytest + ruff + mypy

Layered cleanly:

```
api/         thin FastAPI routers; no business logic
services/    orchestration: session work, signing, gate, append, settlement
domain/      pure types + hash helpers; zero I/O
```

The same `domain/provenance.py` canonical-JSON + hash routine is used by the
server when appending and by `scripts/verify_statement.py` when verifying
offline. There is exactly one implementation — if those two drifted, every
verification would silently break.

## The consent-policy model

`ConsentPolicy` is not a boolean and is not mutable. It carries:

- `artist_id` and a per-artist monotonic `version`
- a list of `ConsentPolicyEntry` rows, one per declared use-type, each with
  `allowed: bool` and an optional `max_weight: float | None`
- `created_at`, optional `notes`

Issuing a new policy creates a row with `version = max(version) + 1` for that
artist. Existing rows are never updated or deleted. Querying by
`(artist_id, version)` gives the historical view audits and statements need:
"under which policy was this generation authorized?" stays answerable forever,
even after the artist updates their stance.

The gate's resolution rules:

| condition                                | result    | reason                                                |
|------------------------------------------|-----------|-------------------------------------------------------|
| artist missing                           | reject    | `artist N not found`                                  |
| no policy on file                        | reject    | `artist N has no consent policy on file`              |
| policy has no entry for the use-type     | reject    | `policy vK does not cover <USE_TYPE>`                 |
| entry has `allowed = False`              | reject    | `artist N denies <USE_TYPE> under policy vK`          |
| entry allowed, no cap                    | grant     | `granted = requested_weight`                          |
| entry allowed, cap exceeded by request   | grant     | `granted = max_weight` (clamped); flagged in reason   |

Absent rows fail closed: silence is not consent.

Overall decision over a list of inputs: all allowed → `ALLOW`; some allowed,
some not → `PARTIAL`; none allowed → `DENY`. Weight caps clamp but don't
strip — the request is still allowed at the reduced weight.

`POST /authorize` is a pure probe — it writes nothing. `POST /generations`
re-runs the same decision function internally before deciding whether to
append, so the gate is single-sourced.

## The provenance log

One row per accepted generation. Each row carries:

```
index, timestamp, initiating_artist_id,
inputs[]   (artist_id, rights_holder_id, use_type, consent_policy_version, weight),
prev_hash, entry_hash, signature, canonical_body
```

The hashing rule:

```
canonical_json(body) = json.dumps(body, sort_keys=True, separators=(',', ':'),
                                  ensure_ascii=False)
entry_hash = sha256(prev_hash || canonical_json(body))
signature  = Ed25519.sign(service_private_key, entry_hash)
```

The genesis entry uses `prev_hash = "0" * 64`. Inputs are sorted by
`(artist_id, use_type)` before canonicalization so the hash is invariant to
the order in which the client supplied them.

The signing keypair is generated on first run, written to `keys/` (gitignored),
and the public PEM is published inside every rights-holder statement so
verification needs no contact with the service.

### Why we store `canonical_body` verbatim

SQLite has no native timezone-aware datetime storage. Round-tripping a
`datetime` through the DB can drop tzinfo and change the ISO-8601 string a
verifier would *re*-build from typed columns — flipping a clean chain to a
"hash mismatch" through no fault of the data. The bytes we signed must travel
with the row, not be reconstructed post-hoc. So `canonical_body` is the
source of truth for hash verification; the structured input rows next to it
exist for indexed settlement joins.

### What tamper-evidence actually means

`GET /provenance/verify` replays the chain top-down and returns the first
tampered index (or `ok: true`). Four kinds of mutation are localized:

| mutation                                          | detected via                                                |
|---------------------------------------------------|-------------------------------------------------------------|
| change a structured input row (e.g. weight)       | structured-row vs. parsed `canonical_body` cross-check      |
| change `canonical_body`                           | `sha256(prev_hash \|\| canonical_body) ≠ stored entry_hash` |
| change `signature`                                | Ed25519 verify fails against `entry_hash`                   |
| change `prev_hash`                                | does not equal previous entry's `entry_hash` in the replay  |

All four are covered by tests under `tests/test_tamper_evidence.py`.

## Settlement

Per consumption event:

```
pool             = units * pool_per_unit
initiating_share = pool * initiating_artist_share        → initiating artist
contributors     = pool - initiating_share               → recorded rights
                                                            holders, distributed
                                                            proportional to
                                                            recorded weight
```

If a generation has zero total weight (every granted weight was 0), the
contributors share is left unallocated rather than retargeted to the
initiating artist — we surface that in the response's `formula` string so the
math stays auditable. The defaults (`pool_per_unit = 1.0`,
`initiating_artist_share = 0.30`) live in `app/config.py`; the formula is
returned with the report so the recipient can re-derive it.

## Rights-holder self-verification

`GET /rights-holders/{id}/statement?period=…` is the rights-holder's audit
view. It includes:

- per-period `total_amount`
- the service's Ed25519 public-key PEM (so recipients verify offline)
- one citation per matching input row in the period, carrying:
  - `generation_index`, `timestamp`, `initiating_artist_id`,
    `consent_policy_version`, `use_type`, `weight`
  - `units_consumed` (this RH's share of the per-generation period total)
  - `amount_for_this_rights_holder`
  - `prev_hash`, `entry_hash`, `signature`, and the verbatim
    `canonical_entry_body` JSON

`scripts/verify_statement.py` is the canonical client-side procedure: it
re-derives `entry_hash` from `prev_hash || canonical_entry_body`, verifies
the Ed25519 signature against the embedded public key, re-derives the dollar
amount from `(weight / total_weight) * units_consumed * pool_per_unit *
(1 - initiating_artist_share)`, and sums to the declared total. Exit 0 only
if every check passes.

The recipient never has to call the service to know their statement is
honest.

---

## Why not a blockchain

The first instinct on encountering "tamper-evident music rights attribution"
is to reach for a blockchain. Don't. The decision was deliberate and is the
intellectual core of this project.

### (a) The hard problem is the oracle problem, not the ledger problem

What needs to be true here is: *the inputs cited on this generation are
exactly the inputs that fed the model, and the consent policy at the moment
of generation actually allowed those uses.* That truth is established
off-chain — by the gate, the model, the operator's pipeline, and the
authorization decision against the registry. A blockchain can only commit,
immutably, to *whatever* facts it is handed. It does not improve the
reliability of the upstream decision; it merely makes a bad decision
permanent. Solving "did the model actually use this stem?" is an oracle
problem, and oracles are where blockchain systems consistently fail. Putting
the same answer on a chain doesn't make it more true.

### (b) The economics are deliberately opaque

The rights-holder counterparties for an Artist-First lab are major labels,
major publishers, and indie aggregators. These institutions negotiate terms
that are non-public on purpose. Per-deal advances, per-use rates, MFN
clauses, cross-catalog discounts, and side letters are competitive
information; they are not going on a public ledger and they are not going on
a "private" L2/L3 with an indexed history either. The technology choice
contradicts the economics. Any blockchain pitch here forces a conversation
about transparency they actively do not want, which kills the deal before the
technical merits get examined.

### (c) Trustlessness among anonymous adversaries is not the property needed

The participants are roughly five named, contractually-bound institutions
that have already signed agreements with each other. They are not anonymous,
they cannot exit, and they can sue. The thing a public chain is *uniquely*
good at — letting anonymous parties who can't sue each other still agree on
shared state — is not the missing ingredient. What's missing is something
much smaller: a way for those named, identifiable counterparties to verify
the operator's accounting against the operator's stored evidence. A signed
hash-chained log plus inclusion proofs delivers exactly that, with two-digit
lines of cryptography and one Python file you can read end-to-end.

### (d) Spotify acquired Mediachain in 2017, and the chain form did not survive

In 2017, Spotify acquired Mediachain Labs — a startup explicitly building
blockchain-based music attribution. The blockchain form of that work did not
become a Spotify product. Pitching "blockchain for rights attribution" to
this specific employer is therefore not a neutral technology choice; it is
proposing to redo something the institution already tried and stepped away
from. That's a credibility problem before it's a technical one.

### What we actually need, and how this delivers it

The properties required are:

- **Tamper-evidence.** Mutating any stored entry must be detectable after
  the fact.
- **Independent verifiability.** Every rights holder must be able to confirm
  the operator's numbers without trusting the operator.
- **Append-only history.** Older states (especially old consent policy
  versions) must remain queryable forever.
- **Cryptographic non-repudiation.** A statement issued by the service must
  be attributable to it.

The signed, hash-chained log delivers all four:

- `entry_hash = sha256(prev_hash || canonical_json(body))` propagates any
  change forward — the chain detects mutation deterministically.
- Statements carry the verbatim canonical body plus the Ed25519 signature
  and the public key PEM, so verification happens entirely on the
  recipient's machine.
- Both the policy table and the provenance log are strictly append-only
  by service contract; the only DDL paths are migrations.
- Signatures are over `entry_hash` with a service-controlled key. The
  operator cannot deny having issued an entry that verifies under their
  public key.

What we *give up* by not using a chain: nothing the use case actually needs.
We do not need anonymous consensus, byzantine-fault tolerance among
adversarial validators, gas-priced ordering, or trustless settlement. We do
need precisely what's here.

This is the right boring answer.
