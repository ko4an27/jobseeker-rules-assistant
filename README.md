# Jobseeker Rules Assistant

Answers jobseekers' questions about Finnish rules and services (unemployment benefits,
side income, pay subsidy, work trial, training, the 2025 employment services reform)
using **only official public pages**, with a citation (URL + section) for every claim.
If the sources don't cover a question, it says so and points to Kela or the employment office.

> Not legal or official advice. Rules change — always check with Kela or your employment office.

The point of the project is the **evaluation**: showing the answers are correct, grounded in
the sources and safe. See `CLAUDE.md` for the rules and `PROGRESS.md` for status.

## How it works (today)

```
sources/urls.txt ──make ingest──▶ sources/*.md   (clean text + URL + fetch date)
                                        │
question ──▶ BM25 search ──▶ top passages ──▶ LLM (sources only) ──▶ safety checks ──▶ answer + citations
```

Safety checks in code: no relevant passage → refuse without calling the LLM; the model says
`NOT_COVERED`, gives no citation, or cites a source it wasn't given → refuse.

## Quick start

```bash
python3 -m venv .venv && . .venv/bin/activate
make install
make test                      # unit tests, never call a real LLM
make ingest                    # fetch missing snapshots (never overwrites)
cp .env.example .env           # add ANTHROPIC_API_KEY, or set LLM_PROVIDER=fake
make ask Q="Can I work part-time while unemployed?"
```

| Variable | Meaning | Default |
|---|---|---|
| `LLM_PROVIDER` | `anthropic` or `fake` (offline, no key) | `anthropic` |
| `LLM_MODEL` | model id | `claude-haiku-5-5` |
| `ANTHROPIC_API_KEY` | secret, only via env / `.env` | — |

`make refresh` re-fetches all snapshots (explicit, overwrites).

## Source tags

`sources/tags.toml` holds our reviewed decisions about pages, separate from the fetched text:
`status = "historical"` (+ `replaced_by`, `note`) for abolished rules, `audience = "employer"` for
pages written for employers, and `weight` (0 excludes a page). Historical pages rank lower, always
bring their replacement page along, and can't be cited alone. Sections that are mostly links
(lines marked `[link]` at ingest) are excluded or down-weighted.
