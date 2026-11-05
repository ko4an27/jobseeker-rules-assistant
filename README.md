# Jobseeker Rules Assistant

Answers jobseekers' questions about Finnish rules and services (unemployment benefits,
side income, pay subsidy, work trial, training, the 2025 employment services reform)
using **only official public pages**, with a citation (URL + section) for every claim.
If the sources don't cover a question, it says so and points to Kela or the employment office.

> Not legal or official advice. Rules change — always check with Kela or your employment office.

The point of the project is the **evaluation**: showing the answers are correct, grounded in
the sources and safe. See `CLAUDE.md` for the rules and `PROGRESS.md` for status.

## How it works

Source pages are saved once (`make ingest`) as clean text with URL and fetch date. Every
question then runs through a LangGraph flow (`src/jobseeker_assistant/graph.py`):

```mermaid
flowchart TD
    Q([question]) --> L{legal_check<br/>personal legal advice?}
    L -- yes --> R([refuse])
    L -- no --> S[retrieve<br/>glossary + BM25, top 8]
    S -- nothing found --> R
    S --> C{coverage_gate<br/>passages match the question?}
    C -- no --> R
    C -- yes --> G[generate<br/>LLM, sources only]
    G -- NOT_COVERED --> R
    G --> V{check_grounding<br/>every claim cited and supported?}
    V -- "no, 1st time" --> GS[generate_strict<br/>retry with stricter rules]
    GS --> V
    V -- "no, after retry" --> R
    V -- yes --> F[finalize<br/>citations + historical notes]
    F --> A([answer + sources + disclaimer])
```

- **No LLM call before the gates:** legal advice, nothing found and low coverage are refused first.
- **Grounding self-check** (`grounding.py`, in code): every sentence that states a fact must
  cite a source it was given; every number in it must appear in that source; most of its key
  words must too. One failure → one retry with stricter instructions and the failing
  sentences; a second failure → refuse.
- **Every refusal** says where to ask instead (Kela, employment services), and records why.

## How to run

Everything below works **without an API key** (fake LLM). Snapshots of the source pages are
already in `sources/`, so nothing needs to be fetched.

```bash
python3 -m venv .venv && . .venv/bin/activate
make install
make test                      # unit + API + graph tests, never call a real LLM
make demo                      # 5 sample questions with the fake LLM: answers + graph paths
make eval                      # golden + held-out sets, dated reports in evals/reports/
```

**API** (FastAPI, docs at http://127.0.0.1:8000/docs):

```bash
LLM_PROVIDER=fake make api
```

```bash
curl -s -X POST http://127.0.0.1:8000/ask -H 'content-type: application/json' \
  -d '{"question": "How long can a work try-out last?"}'
```

`/ask` is rate limited per client (`RATE_LIMIT_PER_MINUTE`, default 10; 429 + `Retry-After`) and,
if `API_KEY` is set, needs the header `X-API-Key` (401 otherwise). Both are for a small server;
behind a proxy or with several replicas, rate limiting needs a shared store instead.

`POST /ask` takes `{"question": "..."}` (1–500 characters) and returns the answer, citations
(URL, section, fetch date), the path through the graph, the refusal reason if any, the number of
LLM attempts and the disclaimer. `GET /health` reports snapshots loaded, LLM and tracing status.
The question text is never logged or stored; logs get only metadata (length, path, reason, latency).

**Docker:**

```bash
make docker-run                # build + serve on http://127.0.0.1:8000 (fake LLM unless .env says otherwise)
```

```bash
make docker-test               # lint + tests inside the image (what CI does)
```

If Docker Hub rate-limits the base image, pass a mirror:
`docker build --build-arg PYTHON_IMAGE=mirror.gcr.io/library/python:3.12-slim .`

**Real model and tracing:** copy `.env.example` to `.env` (git-ignored) and fill in keys.
`make ask`, `make api`, `make eval-real` and `make judge-calibrate` read `.env` automatically;
variables already set in your shell win.

| Variable | Meaning | Default |
|---|---|---|
| `LLM_PROVIDER` | `gemini` or `groq` (free tiers), `anthropic`, or `fake` (offline, no key) | `anthropic` |
| `LLM_MODEL` | model id | gemini `gemini-3.7-flash` (cheaper: `gemini-3.5-flash-lite`), groq `llama-3.3-70b-versatile`, anthropic `claude-haiku-5-5` |
| `LLM_THINKING_LEVEL` | Gemini 3.x thinking: `minimal`/`low`/`medium`/`high` (thinking tokens are billed as output) | Flash-Lite `minimal`, Flash `low` |
| `LLM_API_KEY` | the provider's key, only via env / `.env` (`ANTHROPIC_API_KEY` also works for anthropic) | — |
| `JUDGE_PROVIDER` / `JUDGE_MODEL` / `JUDGE_API_KEY` | optional: a different model as judge | same as `LLM_*` |
| `EVAL_MAX_CALLS` | at most this many real model calls per eval run | `200` |
| `LLM_PRICE_INPUT_PER_MTOK` / `LLM_PRICE_OUTPUT_PER_MTOK` | prices for paid providers (cost report) | free tiers: 0 |
| `LANGFUSE_ENABLED` | `true` turns Langfuse tracing on | off |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST` | Langfuse keys and server | — |
| `LANGFUSE_LOG_TEXT` | `true` also sends question + answer text (default: metadata only) | off |
| `RATE_LIMIT_PER_MINUTE` | `/ask` requests per client per minute (`0` = off) | `10` |
| `API_KEY` | if set, `/ask` needs header `X-API-Key: <key>` | off |

With tracing off, the Langfuse package is not even imported, so nothing is sent anywhere.

Other commands: `make ask Q="..."` (one question on the command line), `make ingest` (fetch
missing snapshots, never overwrites), `make refresh` (explicitly re-fetch all), `make sweep`
(refusal cutoff table, golden set only).

### Evaluate with a real model (free tier)

1. **Get a free key** from Google AI Studio (Gemini) or the Groq console.
2. **Put it in `.env`** (git-ignored):

   ```
   LLM_PROVIDER=gemini
   LLM_API_KEY=your-key-here
   ```

   Model names change; if the default is retired, set `LLM_MODEL`.

   **Use a different model as judge**, so a model doesn't grade its own answers:

   ```
   LLM_MODEL=gemini-3.5-flash-lite      # answers
   JUDGE_MODEL=gemini-3.7-flash         # judges (same provider: reuses LLM_API_KEY)
   ```

   Or another provider entirely: `JUDGE_PROVIDER=groq`, `JUDGE_API_KEY=...`. If the judge is
   the same model as the answerer, the run prints a warning and the report says so.
3. **Review the judge's calibration labels** in `evals/judge_calibration.yaml` (10 answers, each
   labelled pass/fail per rubric criterion). They are a draft: change any you disagree with and
   set `reviewed: true`. Then check the judge agrees with you:

   ```bash
   make judge-calibrate
   ```

   It prints agreement per criterion and every disagreement with the judge's reason, and saves
   a report in `evals/reports/`. Don't trust judge scores on a criterion it disagrees with you on.

   **Known judge weakness: Grounded is lenient.** In the first calibration
   (`gemini-3.5-flash-lite` judging, 2026-11-05) the judge agreed with the human labels on the
   overall verdict for 10/10 answers and on 50/53 individual checks, but passed *Grounded* for
   two answers that should fail it: "EUR 37.21 per **month**" (the source says per day) and
   "your employer is **guaranteed** 50%" (the source says "in most cases"). It treats "the
   number comes from the source" as grounded even when the unit or framing around it changed.
   Both answers still failed overall through *Meaning preserved*, so the overall verdict held.
   That is why the **code-based grounding check stays as the backstop**: before an answer is
   shown, `grounding.py` requires every number in a claim to appear in the cited passage and
   most of its words to match, with one strict retry and then a refusal. The judge only
   *scores* answers; it never decides what users see.
4. **Run the evaluation:**

   ```bash
   make eval-real
   ```

   Golden (38) and held-out (15) questions, answered by the real model and scored by the judge
   against `evals/judge_rubric.md`. A dated report per set goes to `evals/reports/`: the exact
   checks as before, plus pass rates per judge criterion and the judge's reason for every failure.

**Limits and cost.** Before starting it prints the plan: cases, the maximum number of model
calls (≤ 3 per question: answer, one grounding retry, judge) and the estimated maximum cost
($0 on free tiers). A run never makes more than `EVAL_MAX_CALLS` (default 200) real calls: at
the limit it stops cleanly, saves what it has (marked ABORTED) and exits with code 3. Responses
are cached per commit, model and prompt (`evals/.cache/`, git-ignored), so rerunning finishes
the remaining questions without paying for the done ones; uncommitted code turns the cache off.
Calls are spaced out for free-tier rate limits (Gemini ~6 s, Groq ~2 s apart), so a full Gemini
run takes up to ~16 minutes. Paid providers: set the two `LLM_PRICE_*` variables, otherwise the
cost is shown as unknown — prices are not hard-coded because they change.

**Privacy.** Free tiers often let the provider use what you send to improve their models; check
the provider's terms. The eval questions contain no personal data. Do not point the public API
(`make api`) at a free tier with real people's questions.

## Results

All numbers come from the reports in `evals/reports/` (fake LLM: it repeats the first sentence of
its top source, so it measures **retrieval and safety**, not answer wording). Golden is the
tuning set; held-out is never used for tuning.

| After… | Golden: off-topic refused | Golden: real answered | Golden: key fact in retrieved text | Held-out: off-topic refused | Held-out: real answered | Held-out: key fact in retrieved text |
|---|---|---|---|---|---|---|
| Day 2 — first eval, old score cutoff | 0/8 | 27/27 | 16/27 | – | – | – |
| Day 2 — coverage gate | **8/8** | 22/27 | 16/27 | – | – | – |
| Day 3 — held-out written (baseline) | 8/8 | 22/27 | 16/27 | 5/5 | 9/10 | 8/10 |
| Day 3 — glossary, legal rule, 8 passages | 8/8 | 25/27 | **25/27** | 5/5 | 9/10 | **10/10** |
| Day 4 — LangGraph + grounding self-check | 8/8 | 25/27 | 25/27 | 5/5 | 9/10 | 10/10 |
| Day 5b — abolished-benefit notes, coverage fix | 8/8 | **30/30** | 29/30 | 5/5 | 9/10 | 10/10 |

Day 5b adds 3 golden cases (35 → 38). Legal-advice questions are refused **by the legal rule**
since Day 3 (5/5 across both sets), not just by low word overlap. Held-out "real answered" never
moved: the one miss ("certificate of partial work ability", coverage 0.47) was not tuned for.

### First run with a real model (2026-11-05)

`gemini-3.5-flash-lite` (free tier, Flash was overloaded that day) answered; the same model
judged (self-judged, so judge scores may be lenient). 98 model calls, $0. Reports:
`evals/reports/2026-11-05T191141Z_gemini_*_flash-lite.md`.

| | Golden (38) | Held-out (15) |
|---|---|---|
| **Judge overall** (every applicable check passes) | **36/38** | **14/15** |
| Exact checks passed (refusal ok + right source cited + key facts in answer) | 35/38 | 13/15 |
| Off-topic refused | 8/8 | 5/5 |
| Real questions answered | 28/30 | 9/10 |
| Key facts in the answer | 28/30 | 8/10 |
| Sent back by the grounding check (strict retry) | 6/38 → 5 fixed, 1 refused | 0/15 |
| Judge per check: correct · grounded · right source · meaning preserved | 28/28 · 28/28 · 28/28 · 28/28 | 9/9 · 9/9 · 9/9 · 9/9 |
| Judge per check: plain language · safe refusal · replaced note | 38/38 · 28/30 · 8/8 | 15/15 · 10/11 · 1/1 |

With the fake model the same sets scored 17/38 and 6/15 on the exact checks: the fake only
repeats one sentence. Of the 5 real failures, 3 are our own checks or labels being too strict
(see PROGRESS.md), not wrong answers.

## What I learned

- **Most failures were retrieval, not the model.** When an answer lacked the key fact, the fact
  was almost always on the right page, just ranked 5th–9th. Giving the model 8 passages instead
  of 4 fixed most of it. Measure where the fact is before blaming the LLM.
- **A relevance score is not a "do we know this?" score.** Search scores grow with question
  length, so a long off-topic question outscored short real ones. Asking "how much of the
  question does the best passage cover?" separated them cleanly.
- **The held-out set keeps you honest.** On golden, 18/27 answers cited the right page; on the
  first held-out run, only 4/10. Numbers tuned on a set are optimistic about that set.
- **Safety rules belong in code, not only in the prompt.** Refusing legal advice, adding the
  "abolished on 1 May 2026" note, refusing uncited claims: each is a few lines of tested code,
  so it cannot depend on the model remembering an instruction.
- **Checks catch my own mistakes too.** The grounding check caught a test answer of mine that
  cited a page for a date it never mentions; a glossary entry I wrote ("TE office" → "TE
  Services") made a real question worse; an answer of just "x" once passed. Each became a test.
- **Look at the data before deciding.** "Pages that are mostly links" turned out not to exist
  (4–17% link text); the problem was link-list *sections*. The fix followed the measurement.
- **The rules move.** Kela replaced two benefits with one on 1 May 2026, after I started. Dated
  snapshots, historical tags and abolished-benefit notes exist because of that.
- **A fake model only gets you so far.** It made every test free and repeatable, but "does the
  answer contain the fact in good plain English?" needs a real model and a judge — next step.

## Evaluation

`evals/golden.yaml` holds 38 questions with expected key facts and source URLs, or "must refuse";
it may be used for tuning. `evals/heldout.yaml` holds 15 more that are never used for tuning.
`make eval` runs both and saves a dated report per set in `evals/reports/` (fake LLM for now).
`make sweep` shows how the refusal cutoff trades off refusing off-topic questions against
answering real ones. Checks: refusal correct, expected source cited, key facts in the answer —
plus two diagnostics (expected source retrieved, key facts in the retrieved text).

## Glossary and legal-advice rule

`sources/glossary.toml` maps Finnish terms and everyday words to the English page wording
(palkkatuki → pay subsidy, side gig → part-time work). It only changes what is searched; each
entry says whether the page itself pairs the terms (`origin = "source"`) or it is our reviewed
mapping (`origin = "reviewed"` + `why`). Questions asking for personal legal advice ("should I
sue", "will I win my appeal") are refused before retrieval (`legal_advice.py`).

## Source tags

`sources/tags.toml` holds our reviewed decisions about pages, separate from the fetched text:
`status = "historical"` (+ `replaced_by`, `note`) for abolished rules, `audience = "employer"` for
pages written for employers, and `weight` (0 excludes a page). Historical pages rank lower, always
bring their replacement page along; when one is cited, the code adds the "replaced by" note and
cites the replacement. Identical passages on several pages are ranked once. Sections that are mostly links
(lines marked `[link]` at ingest) are excluded or down-weighted.
