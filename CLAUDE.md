# Jobseeker Rules Assistant — project rules for Claude Code
 
## What this is
An AI assistant that answers jobseekers' questions about Finnish rules and services
(unemployment benefit, side income, palkkatuki, työkokeilu, training, the 2025 employment
services reform) using ONLY official public pages (Kela, Työmarkkinatori, municipalities).
Every answer cites its sources. If the sources don't cover the question, it says so and
points to the right office instead of guessing.
 
The main point of the project is the EVALUATION: proving the answers are correct,
grounded in the sources and safe. Built as a portfolio project for a GenAI Specialist role
(insurance customer service has the same problem: rules, policies, no room for invented answers).
 
## Stack
- Python 3.12, uv or pip + requirements.txt
- LangGraph for the agent flow
- FastAPI for the API
- pytest for tests
- Langfuse for tracing (optional, off by default; keys only via env vars)
- Docker + GitHub Actions CI
- LLM provider is configurable via env vars (Anthropic by default; a cheap model for
  development). Tests in CI must NOT call a real LLM: use a fake/stub model.
## Rules (always follow)
1. Small steps: one feature per step, then stop and explain what changed in plain English.
   I review every pull request.
2. Every new function gets a test. Run `pytest` before saying a task is done.
3. Answers may use ONLY retrieved source text. Each claim needs a citation (URL + section).
   No source → answer "I can't confirm this from official sources" + where to ask.
4. Never present the assistant as legal or official advice. Every answer ends with a short
   note: rules change, check with Kela / your employment office.
5. No personal data: the assistant never asks for or stores names, IDs, income figures.
6. Source pages are stored as snapshots with URL and fetch date. Re-fetching is a separate,
   explicit command.
7. Secrets only via environment variables. Never commit keys. `.env` is git-ignored.
8. Evals are first-class: golden test set in `evals/`, results saved per run so regressions
   are visible.
9. At the end of every session, update `PROGRESS.md` (done / next / open questions).
## Evaluation (what "good" means)
- Correctness: the answer matches the expected key facts in the golden set
- Groundedness: every claim is supported by the cited source text (no hallucinations)
- Citation accuracy: cited URLs really contain the claim
- Refusal: out-of-scope or uncovered questions get a safe "can't confirm" answer
- Tone: plain language, short, no legal promises
Methods: exact checks where possible, LLM-as-judge with a written rubric where not,
and a regression report comparing runs.
## Commands (to be added as the code appears)
- `make ingest` — fetch/refresh source snapshots
- `make test` — unit tests (no real LLM)
- `make eval` — run the golden set against the real model, save a report
- `make api` — start FastAPI locally
 