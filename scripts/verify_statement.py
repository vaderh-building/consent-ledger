#!/usr/bin/env python3
"""Offline verifier for a rights-holder statement.

Reads a statement JSON file (the body of GET /rights-holders/{id}/statement?period=…)
and re-derives everything that matters WITHOUT contacting the service:

  1. For each citation, recompute entry_hash = sha256(prev_hash || canonical_entry_body)
     and check it equals the citation's entry_hash.
  2. Verify the Ed25519 signature on entry_hash using the embedded public key.
  3. Re-derive the dollar amount the rights holder is owed for that generation,
     using only fields the statement carries (units_consumed, weight, the
     parsed canonical body, and the policy parameters).
  4. Sum re-derived amounts and check that the total matches the statement's
     declared total_amount.

Exit code 0 iff every check passes. Print a short PASS/FAIL line per citation
plus a final summary.

Usage:
    python scripts/verify_statement.py path/to/statement.json
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

TOL = 1e-6


def _load_public_key(pem: str) -> Ed25519PublicKey:
    key = serialization.load_pem_public_key(pem.encode("ascii"))
    if not isinstance(key, Ed25519PublicKey):
        raise SystemExit("statement public_key is not Ed25519")
    return key


def _verify_signature(pub: Ed25519PublicKey, signature_hex: str, message: bytes) -> bool:
    try:
        pub.verify(bytes.fromhex(signature_hex), message)
    except InvalidSignature:
        return False
    return True


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <statement.json>", file=sys.stderr)
        return 2

    statement = json.loads(Path(argv[1]).read_text())
    pub = _load_public_key(statement["service_public_key_pem"])
    pool_per_unit = float(statement["pool_per_unit"])
    initiating_share = float(statement["initiating_artist_share"])
    declared_total = float(statement["total_amount"])

    citations = statement["citations"]
    print(
        f"Verifying statement for rights holder {statement['rights_holder_id']} "
        f"({statement['rights_holder_name']!r}) over period {statement['period']!r} "
        f"— {len(citations)} citation(s); chain head {statement['head_hash'][:12]}…"
    )

    rederived_total = 0.0
    all_ok = True
    for c in citations:
        idx = c["generation_index"]
        prev_hash = c["prev_hash"]
        canonical = c["canonical_entry_body"]
        entry_hash_claimed = c["entry_hash"]

        recomputed = hashlib.sha256(
            prev_hash.encode("ascii") + canonical.encode("utf-8")
        ).hexdigest()
        hash_ok = recomputed == entry_hash_claimed
        sig_ok = _verify_signature(pub, c["signature"], entry_hash_claimed.encode("ascii"))

        body = json.loads(canonical)
        total_weight = sum(i["weight"] for i in body["inputs"])
        contributors_share = c["units_consumed"] * pool_per_unit * (1.0 - initiating_share)
        rederived = (
            (c["weight"] / total_weight) * contributors_share if total_weight > 0 else 0.0
        )
        amount_ok = abs(rederived - c["amount_for_this_rights_holder"]) < TOL
        rederived_total += rederived

        flag = "PASS" if (hash_ok and sig_ok and amount_ok) else "FAIL"
        if flag == "FAIL":
            all_ok = False
        print(
            f"  [{flag}] gen={idx} use={c['use_type']} "
            f"hash={'ok' if hash_ok else 'BAD'} "
            f"sig={'ok' if sig_ok else 'BAD'} "
            f"amount={'ok' if amount_ok else 'BAD'} "
            f"(claim={c['amount_for_this_rights_holder']:.6f} rederived={rederived:.6f})"
        )

    total_ok = abs(rederived_total - declared_total) < TOL
    print(
        f"Total: declared={declared_total:.6f} rederived={rederived_total:.6f} "
        f"-> {'OK' if total_ok else 'MISMATCH'}"
    )
    if not (all_ok and total_ok):
        print("STATEMENT VERIFICATION FAILED")
        return 1
    print("STATEMENT VERIFIED")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
