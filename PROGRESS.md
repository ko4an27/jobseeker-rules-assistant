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

- 2026-11-04 (Day 3 prep — held-out set, glossary, legal rule, recall):
  - Held-out set `evals/heldout.yaml`: 15 new cases (10 in scope, 5 out of scope), committed before
    any Day 3 change (commit 4ec1905). `make eval` reports golden and held-out separately;
    `make sweep` (tuning) only reads golden.
  - Glossary `sources/glossary.toml`: 21 entries. 12 come from the pages ("general social security
    benefit (yleistuki)", checked by a test); 9 are reviewed mappings with a reason (palkkatuki,
    työkokeilu, työvoimakoulutus are not on any English page; "side gig", "tryout", …). Retrieval gets
    the page wording added; the coverage check sees it instead of the term.
  - Legal-advice rule (`legal_advice.py`): "should I sue", "will I win", "my chances", "is my … legal"
    are refused before retrieval. Every refusal now records its reason; the 5 legal cases (3 golden,
    2 held-out) must be refused by this rule.
  - Recall diagnosis: in all 9 misses the key fact was on an expected page but ranked 5th–9th (one
    17th); once (side-part-time) the right section ranked 1st but the fact was in its second part.
    Never the wrong page. Fix: give the model 8 passages instead of 4; the coverage gate still looks
    at the top 4 (what it was tuned on). Bigger chunks helped too but would shift every coverage value.
  - One glossary entry made a case worse ("TE office" → "TE Services"; "TE Office" is page wording);
    fixed, with a test that reviewed entries don't rewrite page wording.

    | Metric | golden: baseline → glossary → final | held-out: baseline → glossary → final |
    |---|---|---|
    | Out-of-scope refused | 8/8 → 8/8 → 8/8 | 5/5 → 5/5 → 5/5 |
    | … by the legal rule (legal cases) | 0/3 → 0/3 → **3/3** | 0/2 → 0/2 → **2/2** |
    | In-scope answered | 22 → 24 → **25**/27 | 9 → 9 → 9/10 |
    | Expected source retrieved | 24 → 27 → 27/27 | 9 → 9 → **10/10** |
    | Key fact in retrieved text | 16 → 20 → **25**/27 | 8 → 8 → **10/10** |
    | Expected source cited (fake LLM) | 18 → 21 → 22/27 | 4 → 5 → 5/10 |

  - 128 tests pass.

## Next
- Day 3: LangGraph flow (retrieve → answer → self-check grounding → refuse if not covered).
- First eval run with a real model, so "cited" and "facts in answer" mean something: the fake LLM
  only cites [S1], which is why held-out "cited" stays at 5/10 although every fact is retrieved.
- Remaining golden misses: `lmt-apply` and `abolished-te-office` (fact ranked below 8);
  `abolished-peruspaivaraha` and `tricky-side-gig` still refused by the coverage gate.
  Held-out: `h-partial-work-ability` refused (coverage 0.495, just under 0.50).

## Open questions
- **Held-out is no longer fully blind:** I wrote the held-out questions and then the glossary and
  the legal rule, so knowing the questions may have shaped them. A truly blind set needs questions
  written by someone else (e.g. 10 real jobseeker questions you collect).
- 8 passages instead of 4 means more text the model could misuse. Watch groundedness in the Day 4
  judge; drop back to 6 if it suffers (6 gave 23/27 facts on golden).
- **Added notes and groundedness:** notes come from `tags.toml`, not from page text. The Day 4 judge
  should check them like any other claim.
- Snapshots should probably store a "valid from" / page-updated date too, not just fetch date.
