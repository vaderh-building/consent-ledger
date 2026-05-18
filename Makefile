.PHONY: install run seed demo test lint typecheck openapi clean reset

VENV ?= .venv
PY = $(VENV)/bin/python
PIP = $(VENV)/bin/pip
UVICORN = $(VENV)/bin/uvicorn
PYTEST = $(VENV)/bin/pytest
RUFF = $(VENV)/bin/ruff
MYPY = $(VENV)/bin/mypy

install:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"

run:
	$(UVICORN) app.main:app --reload --port 8000

seed:
	$(PY) scripts/seed.py

demo: reset
	$(PY) scripts/demo.py

test:
	$(PYTEST) --cov=app/domain --cov=app/services --cov-report=term-missing

lint:
	$(RUFF) check .

typecheck:
	$(MYPY) app

openapi:
	$(PY) scripts/export_openapi.py

reset:
	rm -f consent_ledger.db
	rm -f keys/service_ed25519.* keys/service_ed25519_pub.* || true

clean: reset
	rm -rf .venv .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov build dist *.egg-info
