# Progress

Goal: GitHub project for the If Generative AI Specialist application — apply ~20.11 (deadline 1.12)

## Plan
- [x] Day 1 — setup (Python, pytest, CI), source snapshots of ~20 official pages, first RAG answer with citations
- [x] Day 2 — golden test set (30–40 questions incl. out-of-scope), simple exact-check evals
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
- 2026-11-04 (Day 2 — golden set and evals):
  - Review decisions applied: TE24 reform page tagged historical. Citing a historical page no longer
    refuses: the code appends the tag's "replaced by … on 1 May 2026" note and cites the replacement
    page itself; it refuses only if the replacement page isn't among the sources.
  - De-duplication: 651 passages hold only 408 distinct texts (shared Työmarkkinatori service cards).
    Identical texts are ranked once: best-scoring copy kept, tags merged (employer warning kept;
    historical only if every copy is historical), other pages listed in `also_on` for evals.
  - Golden set `evals/golden.yaml`: 35 cases (17 current, 5 abolished, 5 tricky, 8 out of scope).
    A test checks every key fact appears in one of its expected source snapshots.
  - `make eval` (fake LLM) saves a dated JSON + Markdown report in `evals/reports/` (never overwrites;
    records commit, `+dirty` if uncommitted). `make sweep` prints the cutoff trade-off.
  - Refusal tuning. A raw BM25 cutoff can't separate the groups ("renew my residence permit at Migri"
    scores 16.4, "What happened to peruspäiväraha?" 3.1). New signal **coverage**: the share of the
    question the best passage matches, rare and unknown words weighing more. Gate at 0.50.

    | Retrieval gate | Out-of-scope refused | In-scope answered |
    |---|---|---|
    | before: score ≥ 1.0 | 0/8 | 27/27 |
    | score-only, best trade-off (≥ 7.5) | 6/8 | 22/27 |
    | after: coverage ≥ 0.50 | **8/8** | 22/27 |

    Any coverage cutoff in (0.45, 0.51] gives the same result; 0.50 sits in the middle of that gap.
  - Fake-LLM eval after tuning: passed 10/35 (8/8 out-of-scope, 2/27 in-scope). Source retrieved 24/27,
    cited 18/27. Key facts in retrieved text 16/27, in answer 2/27 (the fake repeats one sentence).
  - 89 tests pass.

## Next
- Day 3: LangGraph flow (retrieve → answer → self-check grounding → refuse if not covered).
- Retrieval recall: key facts are in the retrieved text for only 16/27 in-scope cases, so even a
  perfect model could answer at most 16. Look at passage size and k before blaming the model.
- Vocabulary gaps cause the 5 false refusals: "side gig", "palkkatuki", "tryout" (typo), "move",
  "happened". Proposal: a small reviewed glossary of official Finnish terms (palkkatuki → pay subsidy,
  työkokeilu → work try-out, yleistuki, työmarkkinatuki, peruspäiväraha, …) for query expansion.
- First eval run with a real model (needs `ANTHROPIC_API_KEY`), so "facts in answer" means something.

## Open questions
- **Rules changed 1 May 2026:** the golden set's `abolished` cases test that the assistant points to
  the general social security benefit. Keep extending them when Kela publishes changes.
- **Cutoff tuned on the same 35 cases it is scored on**, so the 8/8 is optimistic. Add a held-out set
  of questions (not used for tuning) before trusting the number. The margin is small: the hardest
  out-of-scope case (residence permit) has coverage 0.45, the weakest kept real case 0.51.
- **Added notes and groundedness:** `abolished-te-office` passes only because the code's added note
  (our text in `tags.toml`) says "employment areas". Notes must be backed by the cited page; the
  Day 4 judge should check notes like any other claim.
- "Kela rejected my application. Will I win if I appeal?" is refused only by the coverage gate.
  Personal legal advice needs its own rule (CLAUDE.md rule 4), not luck in retrieval.
- Snapshots should probably store a "valid from" / page-updated date too, not just fetch date.
