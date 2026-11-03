PY ?= python3

.PHONY: install test lint format ingest refresh ask

install:            ## install runtime + dev dependencies
	$(PY) -m pip install -r requirements-dev.txt

test:               ## unit tests, never call a real LLM
	$(PY) -m pytest -q

lint:               ## static checks
	$(PY) -m ruff check .
	$(PY) -m ruff format --check .

format:
	$(PY) -m ruff format .
	$(PY) -m ruff check --fix .

ingest:             ## fetch snapshots that don't exist yet (never overwrites)
	PYTHONPATH=src $(PY) -m jobseeker_assistant.ingest

refresh:            ## explicitly re-fetch ALL snapshots (overwrites)
	PYTHONPATH=src $(PY) -m jobseeker_assistant.ingest --refresh

ask:                ## make ask Q="Can I work part-time while unemployed?"
	PYTHONPATH=src $(PY) -m jobseeker_assistant.cli "$(Q)"
