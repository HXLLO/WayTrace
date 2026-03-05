# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

WayTrace is a passive OSINT reconnaissance tool that reconstructs the digital history of any domain using the Wayback Machine (archive.org). It fetches archived HTML pages, selects diverse snapshots across time, and extracts 10 categories of intelligence data with temporal metadata (`first_seen`/`last_seen`). **No active scanning** — only public data from archive.org.

## Commands

### Development (Manual)
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env
uvicorn main:app --reload   # http://localhost:8000
```

### Development (Docker, hot reload)
```bash
cp .env.example .env
docker compose -f docker-compose.dev.yml up
```

### Production
```bash
cp .env.example .env
docker compose up -d   # port 8000
```

### Tests
```bash
cd backend
python -m pytest tests/ -v                    # all tests
python -m pytest tests/test_extractor.py -v   # extractor only
python -m pytest tests/test_filters.py -v     # filters only
python -m pytest tests/test_api.py -v         # API only
```

## Architecture

```
Browser → FastAPI (main.py)
            ├── POST /api/scan/preflight  → CDX query only (no scraping)
            ├── POST /api/scan            → full pipeline → returns job_id
            └── GET  /api/jobs/{id}       → poll status/results

Full scan pipeline (4 phases):
  1. cdx.py      — CDX API client, HTML-only, paginated (resumeKey)
  2. filters.py  — Smart snapshot selection (path scoring + depth presets)
  3. scraper.py  — Concurrent Wayback downloader (semaphore + random delays)
  4. extractor.py — OSINT extraction: 10 categories via regex + selectolax DOM
```

**State**: In-memory only (`store.py`), no database. Jobs auto-expire (TTL=2h, max 25 min runtime). Duplicate domain submissions return the same job ID.

**Frontend**: Single HTML file (`frontend/index.html`) — vanilla JS, dark theme, tabs, export (JSON/CSV), polling every 2s.

## Key Design Decisions

- **selectolax** (C-based parser) over BeautifulSoup — use it for all HTML parsing
- **loguru** for all logging — never use stdlib `logging`
- **Pydantic v2** for all schemas (`models.py`) and config (`config.py` via `pydantic-settings`)
- **Async throughout** — all I/O via `aiohttp`, never blocking calls in async context
- Rate limiting via `asyncio.Semaphore` + adaptive delays (0.02–0.08s base, auto-increases on 429s)

## Snapshot Filtering Logic

Paths are scored by OSINT value (high=3: contact/about/admin/team/login…, medium=2: homepage `/`, low=1: everything else). Depth presets (`quick`/`standard`/`full`) multiply the adaptive cap. Deduplication drops snapshots with identical CDX digest for the same path.

## Extractor Plugin Pattern

To add a new extraction category:
1. Add regex at top of `backend/services/extractor.py`
2. Add extraction logic in `_extract_page()`
3. Initialize accumulator in `extract_all()` `accum` dict
4. Add output formatting in the return statement
5. Write ≥5 positive + ≥5 false-positive tests in `tests/test_extractor.py`

Every extracted entity must include `first_seen`, `last_seen`, `occurrences`.

## Severity Ranking (Highlights)

- **CRITICAL**: API keys or cloud buckets exposed
- **HIGH**: Internal emails, subdomains, sensitive endpoints (/api, /admin, /login, /auth)
- **MEDIUM**: Analytics trackers (cross-domain correlation), tech stack changes, persons
- **LOW**: Social profiles

## Environment Variables (`.env`)

| Variable | Default | Description |
|---|---|---|
| `MAX_CONCURRENT_SCRAPES` | `30` | Parallel Wayback requests (1–50) |
| `ARCHIVE_REQUEST_TIMEOUT` | `30` | Per-request timeout (s) (5–120) |
| `ARCHIVE_RETRY_COUNT` | `3` | Retries on CDX/Wayback failure |
| `SCRAPE_DELAY_MIN` | `0.02` | Min delay between requests (s) |
| `SCRAPE_DELAY_MAX` | `0.08` | Max delay between requests (s) |
| `SCRAPE_MAX_RETRIES` | `3` | Retries per page scrape on transient errors |
| `JOB_TTL_SECONDS` | `7200` | Job expiry (2 hours) |
| `MAX_ACTIVE_JOBS` | `10` | Concurrent scan limit |
| `SCAN_TIMEOUT_SECONDS` | `3600` | Max scan duration (60 min) |
| `PAGE_CACHE_MAX_MB` | `512` | Max page cache size in memory |
| `CDX_CACHE_TTL` | `300` | CDX cache lifetime (s) |
| `PRESCRAKE_LIMIT` | `15` | Max pages to pre-scrape during preflight |
| `COLLAPSE_THRESHOLD` | `250000` | CDX results threshold for month-collapse |
| `SCAN_RATE_LIMIT_RPM` | `10` | Scan requests/min per IP (0=disabled) |
| `CORS_ORIGINS` | `localhost:5173,3000` | Comma-separated allowed origins |
| `LOG_LEVEL` | `INFO` | `DEBUG`/`INFO`/`WARNING`/`ERROR` |

## Branch Strategy

- `main` — stable releases only
- `develop` — integration branch (PR target)
- `feature/*` — feature branches
- `front` — frontend team branch

## Commit Conventions

`feat:` / `fix:` / `refactor:` / `test:` / `docs:` / `chore:`

**IMPORTANT — No AI attribution in commits:** Never add `Co-Authored-By` lines, `Signed-off-by`, or any other trailer/mention referencing Claude, Anthropic, or any AI assistant in commit messages. AI tools must not appear as contributors in the git history. Commit messages must look like they were written by a human developer — no AI branding, no AI credits, nothing.
