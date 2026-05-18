"""Runtime configuration. Kept tiny on purpose — single-file SQLite, local Ed25519 key.

Env overrides (set BEFORE importing app.* modules):
  CONSENT_LEDGER_DB_URL   — full SQLAlchemy URL (defaults to ./consent_ledger.db)
  CONSENT_LEDGER_KEYS_DIR — directory holding the Ed25519 keypair (defaults to ./keys)

Tests use these to get hermetic per-test DB files and key directories.
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent

DATABASE_URL: str = os.environ.get(
    "CONSENT_LEDGER_DB_URL", f"sqlite:///{PROJECT_ROOT / 'consent_ledger.db'}"
)

KEYS_DIR: Path = Path(os.environ.get("CONSENT_LEDGER_KEYS_DIR", str(PROJECT_ROOT / "keys")))
PRIVATE_KEY_PATH: Path = KEYS_DIR / "service_ed25519.pem"
PUBLIC_KEY_PATH: Path = KEYS_DIR / "service_ed25519_pub.pem"

# Settlement parameters. Pool size is per consumption unit (e.g. cents per stream
# in a hypothetical model — units are abstract here).
SETTLEMENT_POOL_PER_UNIT: float = 1.0
# Fixed share routed to the initiating artist (creator of the generation) before
# the remainder is distributed to contributing rights holders by recorded weight.
INITIATING_ARTIST_SHARE: float = 0.30
