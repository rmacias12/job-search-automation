# AGENTS.md — Job Search Automation

Canonical guidance for **any AI agent** (Claude Code, Hermes, Codex, Cursor…) working in this
repository. `CLAUDE.md` is a thin pointer to this file. When behavior or architecture changes,
**update this file** — an agent should be able to orient in one read.

## Project Overview

Full-stack job-search pipeline for the repo owner: **Adzuna API → SQLite → keyword (+ optional
semantic) matching → CLI / React dashboard review → optional Notion kanban**.

Owner profile driving all defaults (illustrative persona — the live profile comes from the
git-ignored `resume_config.json`): **clinical informatics / health-data analyst** (10+ years,
hospital systems and provider networks). **Not** management-track, **no relocation**.
Targets: **$85k–$125k**, **US remote** or **Columbus, OH hybrid**. Search, scoring, and
filtering should reflect clinical informatics / health-data roles — never water results down
with generic keyword-stuffing, and never invent qualifications.

## Commands

```bash
# Everything runs through the project venv (don't assume an activated shell):
PYTHONDONTWRITEBYTECODE=1 venv/bin/python -m unittest discover -s tests -v   # 65 tests
./jobsearch --help                       # wrapper (activates venv itself)
venv/bin/python src/cli.py --help

# Search (real data): salary_min from resume_config, last 30 days, newest first
venv/bin/python src/cli.py --search-profile all --max-results 10
venv/bin/python src/cli.py --search "clinical informatics analyst" --location "Columbus"
venv/bin/python src/cli.py --match --display --limit 15          # keyword scoring
venv/bin/python src/cli.py --match --semantic                    # + OpenAI embeddings (if key configured)
venv/bin/python src/cli.py --pipeline | --stats | --list --status applied

# Dashboard
venv/bin/python api_server.py            # FastAPI on 127.0.0.1:8000 (JOB_API_HOST to override)
cd web && npm run dev                    # Vite on :5173, proxies to :8000; npm run build for dist/

# Notion
venv/bin/python src/cli.py --sync-notion                  # push top 50 matches (→ ~40 unique pages)
venv/bin/python src/cli.py --sync-notion --pull           # pull statuses Notion → SQLite
venv/bin/python src/cli.py --sync-notion --dry-run        # previews (push dry-run is informational only)
```

## Architecture

### Backend (Python, `src/`)
- **`cli.py`** — orchestrator; search profiles live here (`leadership`, `technical`, `hands_on`, `consulting`, `ai`, `all`)
- **`database.py`** — SQLite schema + CRUD; call **`ensure_schema()`** before DB work (creates if missing, migrates columns in place)
- **`job_searcher.py`** — Adzuna wrapper (`JobSearchError` sanitized errors; `infer_remote_status`) + `MockJobSearcher` (explicit `--mock` only)
- **`matcher.py`** — `KeywordMatcher`: gates + weighted scoring, emits `evidence` dict
- **`embedding_matcher.py`** — `HybridMatcher`/`EmbeddingMatcher` (OpenAI `text-embedding-3-small`; activates only when `OPENAI_API_KEY` resolves)
- **`tracking.py`** — application pipeline (`ApplicationTracker`)
- **`notion_sync.py`** — push/pull; `_build_page_index()` (one paginated scan per sync), 0.34s write throttle
- **`resume_parser.py`** — PDF → `resume_config.json`
- **`credentials.py`** — 1Password `op://` resolver (see Credentials)
- **`api_server.py`** (repo root) — FastAPI for the web UI

### Frontend (React + TS, `web/src/`)
- `App.tsx` (layout/state) · `components/` (JobList, JobCard, StatsPanel, filters) · `hooks/useJobs.ts` · `types/job.ts`

### Data layer
- **`data/job_search.db`** (SQLite) — **source of truth**. Tables: `jobs`, `matches`, `applications`, `resumes`, `blacklist`
- **`resume_config.json`** — parsed CV + search preferences (skills, `primary_skills`, `preferred_titles`, targets, gates)
- **`data/backups/<stamp>/`** — verified backups (git-ignored)
- **Notion** — visual kanban only; SQLite wins conflicts

## Data Model & Status Flow

- **jobs**: deduped on Adzuna's stable provider id (`adzuna_<numeric id>`) — never hash redirect URLs
  (tracking params break dedup). `posted_date` comes from the API's `created` field. `remote_status`
  is inferred from ad text (`remote`/`hybrid`/`unknown`). `salary_is_predicted` marks Adzuna-estimated pay.
- **matches**: `UNIQUE(job_id, resume_id)`; `insert_match` is an **upsert that preserves user-managed
  statuses** (`interested`/`applied`/interview stages/`offer`/`rejected`/`withdrawn`/`not_interested`/`blacklisted`) and their notes.
  Only machine-owned statuses (`new`/`auto_rejected`) are recomputed. Row ids are stable → `applications` never dangle.
  `evidence` column: JSON `{found_skills, skills_basis, remote, salary_unknown, salary_predicted, gate_failures}`.
- **Status flow**: `new → interested → applied → phone_screen → technical_interview → final_interview → offer`,
  plus `rejected` (employer declined — user-owned), `withdrawn`, `not_interested` (user triage),
  `auto_rejected` (machine gate-failure), and `blacklisted` (user-deleted).
  - `auto_rejected` = gate failure (salary/location/exclusions) — machine-owned, reasons in notes +
    evidence, **hidden from API/UI by default**, recomputed on re-match
  - `not_interested` = user triage decision — preserved forever, hidden from default views, syncs
    to Notion as the "Not Interested" select option and pulls back
  - `blacklisted` = user-deleted; blocks re-insert via `blacklist` table; excluded from Notion sync
  - Response-rate stats count only the applied pipeline (applied + heard back); `auto_rejected` and
    `not_interested` never enter the denominator

## Matching & Scoring

Weights: **40% skills** (coverage of `primary_skills` with alias matching — a broad resume is not
penalized for skills short ads omit) · **25% title** (`preferred_titles` token coverage + senior-IC
bonus for senior/staff/principal/lead/architect markers) · **20% location** (remote inferred from ad
text, or preferred city; hybrid = 70) · **15% salary** (≥ target min = 100; overlapping range 60–90;
unknown = 50 neutral).

Hard gates (fail → `rejected`): missing `required_skills`; `excluded_keywords` (**multi-word phrases
supported**); location not remote-capable/preferred city; job salary max < `target_salary_min`.
Save thresholds: `min_match_score` (10), `min_semantic_score` (15, semantic runs only).

## API Endpoints (`api_server.py`)

| Endpoint | Method | Notes |
|---|---|---|
| `/api/jobs` | GET | Excludes `blacklisted`, `auto_rejected`, `not_interested` unless explicitly filtered; returns evidence, posted_date, remote_status, salary_is_predicted |
| `/api/stats` | GET | Response rate = heard-back / applied-and-beyond (`applied` alone is NOT a response) |
| `/api/jobs/{match_id}/status` | PUT | Status validated against pipeline vocabulary |
| `/api/jobs/{match_id}` | DELETE | Soft-delete → blacklisted + dedup entry |
| `/api/export` | POST | Writes `web/public/jobs.json` |

Binds **127.0.0.1** by default (`JOB_API_HOST` to override).

## Credentials

- `credentials.json` (git-ignored) holds 1Password `op://vault/item/field` references;
  `src/credentials.py` resolves via `op read`. `NOTION_DATABASE_ID` is a plain id.
- Precedence: explicit constructor arg → `credentials.json` → legacy env var. Resolution **fails
  closed**; `.env` is not auto-loaded; non-interactive shells don't see `~/.zshrc` exports.
- `ADZUNA_APP_ID` lives in `credentials.json` as a **plain value** — it is an identifier, not the
  secret (the API key remains an `op://` reference). The legacy `~/.zshrc` exports for
  `ADZUNA_APP_ID` and `NOTION_DATABASE_ID` were commented out (2026-11-02): `credentials.json` is
  the single source of truth, verified to resolve with those env vars absent (both API clients
  construct and Notion `test_connection` passes in a cleared environment).
- Never print resolved secrets; never surface raw HTTP error text (Adzuna request URLs embed keys —
  use `JobSearchError` sanitized messages).

## Safety Rules for Agents

1. **No mock data into the real DB.** `--mock` is an explicit opt-in; there is no silent fallback.
2. **Back up before destructive DB work**: `data/backups/<timestamp>/` + `PRAGMA integrity_check`
   + logical checksum verification before and after (see git history for the reset pattern).
3. **Adzuna free tier = 100 requests/day.** Budget searches. Defaults: `max_days_old=30`,
   `sort_by=date`. API quirk: `sort_by=date` + `sort_dir=down` returns **HTTP 400** despite docs —
   omit `sort_dir`. Never send `salary_max` to the API (would hide above-target payers).
4. **Notion**: build the page index once per sync; throttle ≥0.34s/write; push cap is 50 matches
   (hardcoded in `cli.py`); archive (reversible) rather than delete stale pages.
5. **Git**: never commit `data/`, `credentials.json`, or backups (all git-ignored). Conventional
   commit messages. Run the test suite before committing behavior changes.
6. Prefer running scratch **script files** over inline `python -c` snippets (agent-terminal
   approval prompts trigger on `-c`/`-e` execution and on protected files like `CLAUDE.md`).

## Testing

65 unit tests (`tests/`): matcher regressions, searcher standardization/errors/pagination, database
upsert + migration + status ownership, CLI search behavior, Notion index/schema, credentials. Run:

```bash
PYTHONDONTWRITEBYTECODE=1 venv/bin/python -m unittest discover -s tests -v
```

This repo has real regression history worth protecting with tests: a `(passes, score)` tuple
unpacking bug capped all scores ~65 for months, and `INSERT OR REPLACE` silently destroyed user
application statuses on re-match. **Every behavior fix gets a regression test.**

## Current State

- DB: live pipeline data stays in `data/job_search.db` (git-ignored). The committed screenshots
  were generated from a seeded **demo** database: 44 fictional jobs, matches
  **16 `new` / 4 `interested` / 7 `applied` / 5 `rejected` / 3 `auto_rejected`**, 118 blacklisted,
  58.8% response rate — every number in docs and screenshots is synthetic.
- Keyword-only scoring active by default; the **semantic layer** activates only when
  `OPENAI_API_KEY` resolves.
- Notion sync: push top matches (top-50 cap); archive (never delete) stale pages.

## Documentation Map

- `AGENTS.md` (this file) — canonical agent guide; keep current
- `CLAUDE.md` — pointer + Claude Code specifics only
- `README.md` — human setup guide (credentials, install)
- `JOB_SEARCH_AUTOMATION_GUIDE.md`, `QUICK_REFERENCE.md` — older human docs; may lag behind this file
