# Why I built this

The Artist-First AI Music lab has signed real deals and made four real
promises. Two of them — artist opt-in over *if and how* their work is used,
and fair compensation with transparent credit — only become real when there
is infrastructure that enforces them. Until then they are PR, and people in
the industry know it. So I built the infrastructure, at the smallest
defensible scope I could, to demonstrate that the property is reachable.

The service is one closed loop: a granular, versioned consent registry; a
pre-generation gate that refuses inputs the cited artists never authorized;
a signed, hash-chained provenance log that records exactly what was used
and under which consent version; a settlement engine that attributes
consumption back through the log and splits a per-unit pool; and a
self-verification statement endpoint that gives every rights holder the
cryptographic material to confirm their own numbers on their own machine.
The chain is verified by replay — mutating any stored entry is detectable
after the fact and the first tampered index is pinpointed. The offline
verifier in `scripts/verify_statement.py` is what makes the property real:
the rights holder doesn't have to trust the operator, and the operator
cannot quietly change history. The demo script walks the entire loop,
including a live tamper-and-detect, in about ten seconds.

The JD describes the role as building "APIs that power AI creation flows,
content consumption, and reporting." This project is exactly those three
endpoints. `POST /authorize` and `POST /generations` are the creation-flow
API the gate sits behind. `POST /consumption-events` is the consumption
intake. `GET /settlement/report` and `GET /rights-holders/{id}/statement`
are the reporting, including the cryptographic proofs that make the
reporting trustworthy. The layering — pure `domain/`, orchestration
`services/`, thin `api/` — is the layering I would want to maintain in a
production codebase that this would grow into, where the operator-side
trust model (key rotation, multi-signer schemes, third-party witnesses,
revocation lists) is the natural next layer up. The pieces here are small
on purpose; the discipline is in keeping them small enough that someone
can read them end to end and tell me where I'm wrong.

— Vader
