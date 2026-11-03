# Progress

Goal: GitHub project for the If Generative AI Specialist application — apply ~20.11 (deadline 1.12)

## Plan
- [x] Day 1 — setup (Python, pytest, CI), source snapshots of ~20 official pages, first RAG answer with citations
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
- 2026-11-03 (Day 1, part 2 — snapshots):
  - Network access granted; `make ingest` → 18 saved, 4 failed (404). Checked the 5 guessed URLs:
    `labour-market-subsidy` was right; 4 were wrong and replaced with the real pages, found via links
    on the fetched pages (`kela.fi/did-you-find-a-job`, `tyomarkkinatori.fi/en/more-information-about-services/`
    `pay-subsidy`, `work-try-out`, `labour-market-training`). One URL updated to its redirect target.
  - Extractor fix: pages without `<main>` no longer fall back to a small promo `<article>`; titles drop the
    " - … - Job Market Finland" suffix. `make refresh` → all 22 snapshots saved, reviewed. 42 tests pass.

## Next
- Day 2: golden test set in `evals/` (30–40 questions incl. out-of-scope), simple exact-check evals.
- Tune refusal: the search-score cutoff (`min_score=1.0`) is too low on real pages — "best pizza in
  Helsinki" matched "the best way to support your employment" and was not refused at search time.
- Try a few real questions with a real key; tune passage size.

## Open questions
- **Rules changed 1 May 2026:** Kela replaced the labour market subsidy and basic unemployment
  allowance with the *general social security benefit* (yleistuki). Old-benefit pages are kept
  as history; the golden set must test that the assistant uses the current rules.
- Historical pages kept on purpose: basic unemployment allowance, labour market subsidy (abolished
  1 May 2026) and a 2024 TE-services news item. Should retrieval down-rank or label them?
- Some pages are long link lists (e.g. "I need help to support my ability to work", 207 bullet lines).
  Fine for now; may add noise to retrieval.
- Pay subsidy page is aimed at employers; jobseeker-side palkkatuki info may need another page.
- Snapshots should probably store a "valid from" / page-updated date too, not just fetch date.
