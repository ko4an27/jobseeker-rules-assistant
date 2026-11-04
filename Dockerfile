# Jobseeker Rules Assistant — API image.
#   make docker-build   build the runtime image
#   make docker-run     serve the API on http://127.0.0.1:8000 (fake LLM unless .env says otherwise)
#   make docker-test    build the test stage and run lint + tests inside it (what CI does)

# Base image can be swapped for a mirror if Docker Hub rate-limits, e.g.
#   docker build --build-arg PYTHON_IMAGE=mirror.gcr.io/library/python:3.12-slim .
ARG PYTHON_IMAGE=python:3.12-slim
FROM ${PYTHON_IMAGE} AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
# Code and the reviewed source snapshots/tags/glossary. No secrets: keys come from env at run time.
COPY src/ src/
COPY sources/ sources/
RUN useradd --create-home --uid 10001 app && chown -R app /app
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status == 200 else 1)"
CMD ["uvicorn", "jobseeker_assistant.api:app", "--host", "0.0.0.0", "--port", "8000"]

FROM runtime AS test
USER root
COPY requirements-dev.txt pyproject.toml ./
RUN pip install -r requirements-dev.txt
COPY tests/ tests/
COPY evals/ evals/
RUN chown -R app /app
USER app
# Tests must never call a real LLM.
ENV LLM_PROVIDER=fake
# (No `make` in the slim image, so the same commands as `make lint test`, run directly.)
CMD ["sh", "-c", "python -m ruff check . && python -m ruff format --check . && python -m pytest -q"]
