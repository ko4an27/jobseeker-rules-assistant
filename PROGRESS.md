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

- 2026-11-03 (source tags, decisions from review):
  - `sources/tags.toml` + `source_tags.py`: per-page status (current/historical), replaced_by, note,
    audience (jobseeker/employer), weight. Kept separate from snapshots so it survives refresh.
  - Historical pages (labour market subsidy, basic unemployment allowance, 2024 TE news) rank at half
    weight; if one is retrieved, its replacement page is added to the sources; an answer citing a
    historical page without its replacement is refused. Prompt labels `[HISTORICAL: …]`.
  - Pay subsidy page tagged `audience = "employer"`; prompt labels `[FOR EMPLOYERS]` and tells the model
    to answer from the jobseeker's point of view.
  - Link lists: measured — no page is mostly links (4–17% link text), so weighting is per section.
    Ingest marks link-only lines `[link]`; sections >60% links are excluded (57 of 651), others are
    down-weighted by their link share. `make refresh` run; page text unchanged apart from the marks.
  - 63 tests pass.

## Next
- Day 2: golden test set in `evals/` (30–40 questions incl. out-of-scope), simple exact-check evals.
- Tune refusal: the search-score cutoff (`min_score=1.0`) is too low on real pages — "best pizza in
  Helsinki" matched "the best way to support your employment" and was not refused at search time.
- Try a few real questions with a real key; tune passage size.
- De-duplicate passages: Työmarkkinatori situation pages embed the same service cards, so e.g.
  "How long can a work try-out last?" gets 4 identical passages; copies of the pay subsidy card on
  other pages don't carry the employer tag.

## Open questions
- **Rules changed 1 May 2026:** Kela replaced the labour market subsidy and basic unemployment
  allowance with the *general social security benefit* (yleistuki). Old-benefit pages are kept
  as history; the golden set must test that the assistant uses the current rules.
- Decided: historical pages stay, marked and ranked lower; abolished-benefit answers cite old + new.
  Link-list sections excluded / down-weighted. Employer pages tagged, answered for the jobseeker.
- `uudistukset24/etusivu` (TE24 reform page) is written in a pre-2025 tense — tag as historical too?
- The "historical needs replacement cited" rule is enforced by refusing; is a refusal the right
  outcome, or should the answer add the replacement note itself? Check with real-model evals.
- Snapshots should probably store a "valid from" / page-updated date too, not just fetch date.
