# Progress

Goal: GitHub project for the If Generative AI Specialist application — apply ~20.11 (deadline 1.12)

## Plan
- [x] Day 1 — setup (Python, pytest, CI), source snapshots of ~20 official pages, first RAG answer with citations
- [x] Day 2 — golden test set (30–40 questions incl. out-of-scope), simple exact-check evals
- [x] Day 3 — LangGraph flow: retrieve → answer → self-check grounding → refuse if not covered
- [~] Day 4 — LLM-as-judge with a rubric (built, needs a real run), regression report between runs
- [x] Day 5 — Langfuse tracing, FastAPI endpoint, Docker (5a, fake LLM)
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

- 2026-11-04 (LangGraph flow):
  - `graph.py`: legal_check → retrieve → coverage_gate → generate → check_grounding →
    (finalize | generate_strict → check_grounding | refuse). `answer_question` runs the graph,
    so the CLI and evals use it unchanged. Every answer records the nodes it went through.
  - `grounding.py`: self-check in code (no extra LLM call). Each sentence that states a fact must
    cite a source it was given; its numbers must be in that source; ≥ 60% of its key words too
    (light stemming). The answer must contain at least one cited claim.
  - One failure → one strict retry (stricter system prompt + the failing sentences and why);
    second failure → refuse ("not_grounded"). NOT_COVERED refuses at once, no retry.
    Missing/invented citations now get the retry too instead of an instant refusal.
  - The check caught a test of mine: a canned answer claimed "replaced on 1 May 2026" citing a
    page that never says so. Fixed the test, not the checker. It also showed a hole: an answer
    of just "x" (no claim, no citation) passed; now an answer needs ≥ 1 cited claim.
  - Graph tests for every path (answer, retry→answer, retry→refuse, legal, nothing found,
    low coverage, NOT_COVERED, replacement unavailable). README has a Mermaid diagram.
  - Eval (fake LLM) unchanged from Day 3: golden 11/35, held-out 6/15; retried 0, because the fake
    quotes its source verbatim. New report lines: `retried`, `refused_not_grounded`.
  - 146 tests pass.

- 2026-11-04 (Day 5a — API, tracing, Docker, demo):
  - `api.py` (FastAPI): `POST /ask` → answer, citations, graph path, refusal reason, attempts,
    disclaimer, request id; `GET /health`. Validation: 1–500 characters, blank rejected (422).
    Not configured (e.g. no API key) → 503 with the reason. Logs carry metadata only; a test
    checks a name, an ID and an income in the question never reach the logs.
  - `tracing.py`: Langfuse off unless `LANGFUSE_ENABLED=true`; when off the package is not even
    imported (tested). When on: keys from env only; metadata only unless `LANGFUSE_LOG_TEXT=true`.
  - Dockerfile: `runtime` stage (non-root, healthcheck, uvicorn) and `test` stage. CI job builds
    both, runs lint + tests inside the image and smoke-tests `/health` and `/ask`. Locally verified:
    174 tests pass in the image, the API container answers. Found and fixed: the slim image has no
    `make`, so the test stage runs the commands directly.
  - `make demo`: 5 questions (incl. off-topic and legal) with the fake LLM, printing answers + paths.
  - 174 tests pass.

- 2026-11-04 (Day 5b — abolished-benefit notes, coverage fix, API protection, README results):
  - `sources/abolished.toml` + `abolished.py`: if the question names the labour market subsidy,
    basic unemployment allowance (also työmarkkinatuki / peruspäiväraha) or the TE Office, the
    answer always ends with the "abolished … 1 May 2026" (TE: "… 1 January 2025") note. It cites
    the passage of a page that states the change (Kela FAQ intro; TE24 page), pulled into the
    sources if needed, and is added only if the grounding check finds it supported. If the
    normal flow would refuse (except legal advice), `note_only` answers with the note instead.
    3 new golden cases (38 total); golden abolished cases 8/8.
  - Coverage: conversational words ("got", "small", "happened", "true", contraction leftovers)
    are ignored by the coverage check — they were rare in the formal pages and weighed like an
    off-topic word. Tuned on golden: real answered 25/27 → 27/27, off-topic still 8/8.
    Held-out unchanged (5/5, 9/10); `h-partial-work-ability` 0.495 → 0.47 (its "get" no longer counts).
  - `/ask`: rate limit (10/min per client, `RATE_LIMIT_PER_MINUTE`, 429 + Retry-After) and an
    optional API key (`API_KEY`, header `X-API-Key`, constant-time compare, 401). `/health` open.
  - README: "Results" table per day (golden vs held-out) and "What I learned".
  - Eval (fake LLM): golden 17/38 passed, 30/30 real answered, 8/8 off-topic refused;
    held-out 6/15, 9/10, 5/5. 204 tests pass.

- 2026-11-05 (Day 6 — free-tier providers, judge, cost guard, eval-real; still no key):
  - Providers: `gemini` and `groq` (free tiers) next to `anthropic`, picked by `LLM_PROVIDER`, key
    from `LLM_API_KEY` (sent in a header, never in URLs or errors). 429/5xx retried with
    Retry-After. Optional separate judge model via `JUDGE_*`; it never borrows another
    provider's key or model.
  - Judge: rubric in `evals/judge_rubric.md` (correct, grounded, right_source, negations,
    plain_language, safe_refusal, replaced_note), inserted into the judge prompt as written. Code
    decides n/a (refusals, must-refuse, no abolished benefit named). Bad judge JSON → recorded
    error, never a crash. `FakeJudge` for tests.
  - `evals/judge_calibration.yaml`: 10 hand-labelled answers (passages copied word for word from
    the snapshots, tested), each bad answer breaking one or two criteria. **Labels are my draft,
    `reviewed: false` until you check them.** `make judge-calibrate` → agreement per criterion.
  - Cost guard (`budget.py`): `EVAL_MAX_CALLS` (default 200) real calls per run; cache per
    commit + model + prompt (off for uncommitted code); estimated and actual cost (free tiers 0;
    paid prices from env, never hard-coded); pacing for free-tier rate limits. At the limit the
    run stops, saves a partial report marked ABORTED, exits 3; a rerun reuses the cache.
  - `make eval-real`: golden + held-out with the real model and the judge, dated reports with
    per-criterion judge pass rates and reasons. Refuses to run with the fake provider.
  - Found and fixed: `.env` was documented but never read (only `make docker-run` used it); now
    loaded at the CLI / API / eval entry points, never overriding the shell, never in tests.
    `save_report` captured its folder at import, so a test wrote into the real reports folder
    (removed, fixed). `.env.example` pinned a Claude model name even for other providers.
  - 253 tests pass.

- 2026-11-05 (Gemini model choice, first real calls):
  - list-models: 61 models visible to the key; stable text Flash with generateContent: 2.5, 3.5,
    3.6, 3.7, 3.8; Flash-Lite: 2.5, 3.1, 3.5. Picked: newest stable Flash `gemini-3.8-flash`, but
    it returned 503 "high demand" on every try, so the default is **`gemini-3.7-flash`**
    (as agreed); cheaper option **`gemini-3.5-flash-lite`**. `-latest` aliases avoided (they move).
  - Thinking: 3.x models reject `thinkingBudget` (HTTP 400) and take `thinkingLevel`; Flash rejects
    "minimal", Flash-Lite accepts it. Now: 3.x Flash `low`, Flash-Lite `minimal`, 2.x budget 0,
    automatic fallback to `low` if a level is rejected, `LLM_THINKING_LEVEL` override. Thinking
    parts are dropped from answers; thinking tokens are counted as (billed) output.
  - Confirmed on the free tier through `GeminiLLM`: `gemini-3.5-flash-lite` → "Hei! Tervehdys!",
    16 in / 7 out / 0 thinking tokens. `gemini-3.7-flash` not yet confirmed (503 overload).
  - Fixed: key masking replaced every occurrence of a short test key inside error text
    ("Thinking" → "Thin***ing"); now only key-sized strings are masked.
  - 260 tests pass.

## Next
- **You:** review the 10 labels in `evals/judge_calibration.yaml`, set `reviewed: true`.
- Get a free Gemini or Groq key; run `make judge-calibrate`, then `make eval-real`.
- Compare the real run with the fake-LLM numbers in the README; watch `retried` and
  `refused_not_grounded` (is the 60% key-word threshold too strict for real paraphrases?).
- Regression report between two real runs (Day 4 plan, second half).
- Day 6 plan: README "How we know it's correct", demo transcript, polish.

## Open questions
- **The judge is unproven** until it has been calibrated against your reviewed labels. A model
  judging its own answers tends to be lenient; use a different `JUDGE_PROVIDER` if possible.
- **Free-tier terms:** providers may use free-tier traffic to improve their models. Fine for the
  eval questions (no personal data); not for real users' questions through the API.
- `gemini-3.7-flash` (default) has not answered yet: 503 overload all afternoon. If it keeps
  failing, run evals with `LLM_MODEL=gemini-3.5-flash-lite` (confirmed working). The Groq default
  (`llama-3.3-70b-versatile`) is still unchecked.
- **TE Office note cites a historical page:** no current page in our sources describes the end of
  the TE Offices; the note cites the TE24 reform page (the only one that states it).
- **Notes count as facts:** abolished-benefit cases pass partly through our reviewed note text.
  It is checked against the cited page before it is added, but the wording is ours.
- Rate limit is per process and keyed by client address: behind a reverse proxy every request
  looks like the proxy, and several replicas would each count separately. Fine for one server.
- **Held-out is no longer fully blind:** I wrote the held-out questions and then the glossary and
  the legal rule, so knowing the questions may have shaped them. A truly blind set needs questions
  written by someone else (e.g. 10 real jobseeker questions you collect).
- 8 passages instead of 4 means more text the model could misuse. Watch groundedness in the Day 4
  judge; drop back to 6 if it suffers (6 gave 23/27 facts on golden).
- **Historical-page notes** (from `tags.toml`, when an old page is cited) are still not checked
  against a page; the abolished-benefit notes now are. The judge should check both.
- **The self-check is lexical:** it catches invented numbers, citations and topics, but not a
  sentence that reuses the source's words to say something different (e.g. a dropped "not").
  That is the judge's job; until then a real-model answer is only as safe as this check.
- Snapshots should probably store a "valid from" / page-updated date too, not just fetch date.
