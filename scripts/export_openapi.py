#!/usr/bin/env python3
"""Dump the FastAPI app's OpenAPI spec to openapi.json at the project root."""

from __future__ import annotations

import json
from pathlib import Path

from app.main import app

OUT = Path(__file__).resolve().parent.parent / "openapi.json"
OUT.write_text(json.dumps(app.openapi(), indent=2))
print(f"wrote {OUT.relative_to(Path.cwd())}  ({OUT.stat().st_size} bytes)")
