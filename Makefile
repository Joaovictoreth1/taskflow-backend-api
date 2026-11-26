PYTHON ?= python

.PHONY: install lint typecheck test audit check migrate run smoke
install:
	$(PYTHON) -m pip install -r requirements-dev.txt

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

typecheck:
	$(PYTHON) -m mypy app seed.py

test:
	$(PYTHON) -m pytest --cov=app --cov-report=term-missing --cov-fail-under=90

audit:
	$(PYTHON) -m pip_audit -r requirements-dev.txt

check: lint typecheck test audit

migrate:
	$(PYTHON) -m alembic upgrade head

run:
	$(PYTHON) -m uvicorn app.main:app --reload

smoke:
	$(PYTHON) scripts/smoke.py
