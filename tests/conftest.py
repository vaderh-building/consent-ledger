"""Test fixtures.

Each test gets its own SQLite file and its own service signing keypair, so the
chain state and the public key are hermetic. We do that by setting env vars
*before* importing app.config and rebuilding the engine accordingly.
"""

from __future__ import annotations

import importlib
import os
import sys
from collections.abc import Iterator

import pytest


@pytest.fixture
def app_modules(tmp_path, monkeypatch) -> Iterator[tuple[object, object, object]]:
    """Yield (app, db, signing) re-imported against a tmp_path-rooted config."""
    db_file = tmp_path / "consent_ledger.db"
    keys_dir = tmp_path / "keys"
    keys_dir.mkdir()

    monkeypatch.setenv("CONSENT_LEDGER_DB_URL", f"sqlite:///{db_file}")
    monkeypatch.setenv("CONSENT_LEDGER_KEYS_DIR", str(keys_dir))

    # Drop every cached app.* module so a clean import picks up the new env vars
    # AND a new SQLAlchemy Base / engine. We sort by depth descending so leaves
    # go before the packages that re-export them.
    for mod in sorted(
        [m for m in sys.modules if m == "app" or m.startswith("app.")],
        key=lambda m: m.count("."),
        reverse=True,
    ):
        del sys.modules[mod]

    config = importlib.import_module("app.config")
    db = importlib.import_module("app.db")
    signing = importlib.import_module("app.services.signing")
    main = importlib.import_module("app.main")

    db.init_db()
    signing.ensure_keypair()

    assert str(db_file) in config.DATABASE_URL
    assert keys_dir.samefile(config.KEYS_DIR)
    assert os.path.exists(config.PRIVATE_KEY_PATH)

    yield main, db, signing

    db.engine.dispose()


@pytest.fixture
def client(app_modules):
    from fastapi.testclient import TestClient

    main, _, _ = app_modules
    with TestClient(main.app) as c:
        yield c


@pytest.fixture
def session(app_modules):
    """Yield a raw DB session for tests that need to bypass HTTP (e.g. tampering)."""
    _, db, _ = app_modules
    s = db.SessionLocal()
    try:
        yield s
    finally:
        s.close()
