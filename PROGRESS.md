# Progress

Goal: GitHub project for the If Generative AI Specialist application — apply ~20.11 (deadline 1.12)

## Plan
- [~] Day 1 — setup (Python, pytest, CI), source snapshots of ~20 official pages, first RAG answer with citations
- [ ] Day 2 — golden test set (30–40 questions incl. out-of-scope), simple exact-check evals
- [ ] Day 3 — LangGraph flow: retrieve → answer → self-check grounding → refuse if not covered
- [ ] Day 4 — LLM-as-judge with a rubric, regression report between runs
- [ ] Day 5 — Langfuse tracing, FastAPI endpoint, Docker
- [ ] Day 6 — README ("How we know it's correct"), demo transcript, polish
- [ ] Message Petr Vanek with the link + apply to If

## Done
- 2026-11-03 (Day 1):
  - Project setup: requirements, pytest, ruff, Makefile, .gitignore (.env ignored), GitHub Actions CI
    (lint + tests on every push, `LLM_PROVIDER=fake` so CI never calls a real model).
  - Snapshot format + `make ingest` / `make refresh` (fetch is separate and explicit; never
    overwrites unless `--refresh`). 22 official URLs listed in `sources/urls.txt`.
  - First RAG answer: BM25 retrieval by section → LLM with numbered sources → code-level checks
    (refuse if no passage / NOT_COVERED / no citation / invented citation) → citations + disclaimer.
  - LLM provider via env vars (Anthropic default, `fake` for offline). 39 unit tests pass.

## Next
- Allow `www.kela.fi` and `tyomarkkinatori.fi` in the cloud environment's network settings,
  run `make ingest`, review snapshots, fix any wrong "inferred" URLs, commit `sources/*.md`.
- Try a few real questions with a real key; tune `min_score` and passage size.
- Day 2: golden test set in `evals/`.

## Open questions
- **Sources blocked:** the session's network policy denies `www.kela.fi` and `tyomarkkinatori.fi`
  (proxy 403), so `sources/` has no snapshots yet. No page content was faked.
- **Rules changed 1 May 2026:** Kela replaced the labour market subsidy and basic unemployment
  allowance with the *general social security benefit* (yleistuki). Old-benefit pages are kept
  as history; the golden set must test that the assistant uses the current rules.
- 5 URLs in `urls.txt` are marked "inferred" (guessed from URL patterns) — confirm on first ingest.
- Snapshots should probably store a "valid from" / page-updated date too, not just fetch date.
