PY ?= python3
IMAGE ?= jobseeker-rules-assistant

.PHONY: install test lint format ingest refresh ask eval eval-real judge-calibrate sweep api demo \
	docker-build docker-run docker-test

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

eval:               ## run golden + held-out sets, save dated reports (fake LLM until a key is set up)
	LLM_PROVIDER=$${LLM_PROVIDER:-fake} PYTHONPATH=src $(PY) -m jobseeker_assistant.evals

eval-real:          ## golden + held-out with the REAL model + LLM judge (needs LLM_PROVIDER, LLM_API_KEY)
	PYTHONPATH=src $(PY) -m jobseeker_assistant.evals --real

judge-calibrate:    ## does the judge agree with the hand labels in evals/judge_calibration.yaml?
	PYTHONPATH=src $(PY) -m jobseeker_assistant.evals --judge-calibrate

sweep:              ## try retrieval cutoffs on the golden set
	PYTHONPATH=src $(PY) -m jobseeker_assistant.evals --sweep

ask:                ## make ask Q="Can I work part-time while unemployed?"
	PYTHONPATH=src $(PY) -m jobseeker_assistant.cli "$(Q)"

api:                ## start the HTTP API on http://127.0.0.1:8000 (docs at /docs)
	PYTHONPATH=src $(PY) -m uvicorn jobseeker_assistant.api:app --host 127.0.0.1 --port 8000

demo:               ## 5 sample questions through the graph with the fake LLM
	LLM_PROVIDER=fake PYTHONPATH=src $(PY) -m jobseeker_assistant.demo

docker-build:       ## build the API image
	docker build --target runtime -t $(IMAGE) .

docker-run: docker-build  ## serve the API from Docker on http://127.0.0.1:8000
	docker run --rm -p 127.0.0.1:8000:8000 \
		$$( [ -f .env ] && echo --env-file .env ) \
		-e LLM_PROVIDER=$${LLM_PROVIDER:-fake} $(IMAGE)

docker-test:        ## run lint + tests inside the image (same as CI)
	docker build --target test -t $(IMAGE):test .
	docker run --rm $(IMAGE):test
