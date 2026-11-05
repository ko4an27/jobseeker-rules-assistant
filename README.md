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

| Variable | Meaning | Default |
|---|---|---|
| `LLM_PROVIDER` | `anthropic` or `fake` (offline, no key) | `anthropic` |
| `LLM_MODEL` | model id | `claude-haiku-5-5` |
| `ANTHROPIC_API_KEY` | secret, only via env / `.env` | — |
| `LANGFUSE_ENABLED` | `true` turns Langfuse tracing on | off |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST` | Langfuse keys and server | — |
| `LANGFUSE_LOG_TEXT` | `true` also sends question + answer text (default: metadata only) | off |
| `RATE_LIMIT_PER_MINUTE` | `/ask` requests per client per minute (`0` = off) | `10` |
| `API_KEY` | if set, `/ask` needs header `X-API-Key: <key>` | off |

With tracing off, the Langfuse package is not even imported, so nothing is sent anywhere.

Other commands: `make ask Q="..."` (one question on the command line), `make ingest` (fetch
missing snapshots, never overwrites), `make refresh` (explicitly re-fetch all), `make sweep`
(refusal cutoff table, golden set only).

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
