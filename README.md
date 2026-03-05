# WayTrace

> **The archive never forgets.**

[Lire en francais](README_FR.md)

Passive OSINT reconnaissance tool that reconstructs the complete digital history of any domain using the Wayback Machine (archive.org). Enter a domain — WayTrace fetches archived HTML pages across decades, intelligently selects the most relevant snapshots, and extracts 10 categories of intelligence data. Every finding includes `first_seen` / `last_seen` timestamps, giving you a full timeline of what appeared, changed, and disappeared over time.

**No active scanning. No brute-forcing. Only public data from archive.org.**

![MIT License](https://img.shields.io/badge/license-MIT-blue)
![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green)
![Tests](https://img.shields.io/badge/tests-90_passing-brightgreen)

---

## Contents

- [How it works](#how-it-works)
- [Scan pipeline](#scan-pipeline)
- [Interface walkthrough](#interface-walkthrough)
- [Extraction categories](#extraction-categories)
- [Key Findings & severity](#key-findings--severity)
- [Quick start](#quick-start)
- [API reference](#api-reference)
- [Configuration](#configuration)
- [Architecture](#architecture)
- [Tests](#tests)
- [Legal & Ethics](#legal--ethics)

---

## How it works

```
  domain input
       |
       v
+---------------------------------------------------------------------+
|  Phase 1 - CDX Query                                                |
|  -------------------------------------------------------------------+
|  Hit archive.org CDX API -> fetch all archived HTML URLs for domain  |
|  Filter: text/html only, status 200, paginated (resumeKey)          |
|  Local gzip cache in data/cdx/ to avoid redundant network calls     |
|  Result: up to 50 000+ snapshot records with timestamps + digests   |
+--------------------------------+------------------------------------+
                                 |
                                 v
+---------------------------------------------------------------------+
|  Phase 2 - Smart Snapshot Selection                                 |
|  -------------------------------------------------------------------+
|  Score every URL path by OSINT value (HIGH / MEDIUM / LOW)          |
|  Deduplicate by CDX digest (skip identical content, keep earliest)  |
|  Apply depth preset multiplier (quick / standard / full)            |
|  Enforce adaptive cap based on domain size                          |
+--------------------------------+------------------------------------+
                                 |
                                 v
+---------------------------------------------------------------------+
|  Phase 3 - Scraping                                                 |
|  -------------------------------------------------------------------+
|  Fetch HTML from Wayback Machine for each selected snapshot         |
|  Concurrent requests (semaphore), adaptive delay between requests   |
|  Automatic backoff on 429 rate-limiting, retries on transient errors|
|  Strip Wayback injected toolbar/scripts before processing           |
+--------------------------------+------------------------------------+
                                 |
                                 v
+---------------------------------------------------------------------+
|  Phase 4 - Extraction & Aggregation                                 |
|  -------------------------------------------------------------------+
|  Parse HTML with selectolax (C-based, ~10x faster than BS4)         |
|  Apply 10 extraction categories (regex + DOM + JSON-LD parsing)     |
|  Aggregate: first_seen, last_seen, occurrences per finding          |
|  Rank highlights by severity (CRITICAL > HIGH > MEDIUM > LOW)       |
+--------------------------------+------------------------------------+
                                 |
                                 v
                    Structured OSINT results
                     with temporal metadata
```

---

## Scan pipeline

### Preflight

Before running a full scan, WayTrace executes a **lightweight preflight** — only Phase 1 (CDX query). No pages are downloaded. The preflight returns:

- Total snapshot count and unique paths
- Date range (first archived to last archived)
- Suggested scan configuration (adaptive cap)
- Per-path snapshot browser with scores (for Advanced mode)

This lets you assess a domain's archive size and adjust settings before committing to a full scan.

### Smart Snapshot Selection

Not all archived pages are equally valuable. WayTrace assigns each URL path an **OSINT score**:

| Score | Paths | Why valuable |
|-------|-------|--------------|
| **HIGH (3)** | `/contact`, `/about`, `/team`, `/staff`, `/people`, `/careers`, `/jobs`, `/login`, `/admin`, `/press`, `/investors`, `/security`, `/partners`, `/privacy`, `/terms`, `/legal`, `/imprint`, `/impressum`, `/blog` | Where emails, names, phone numbers, and internal endpoints typically appear |
| **MEDIUM (2)** | Homepage `/` | Tracks branding, tech stack, and ownership changes over time |
| **LOW (1)** | Everything else | General content |

**Content deduplication** — CDX provides a SHA-1 digest for each snapshot. Snapshots with the same `path + digest` are collapsed to the earliest occurrence, avoiding redundant scrapes of identical pages. Can be toggled off via the `smart_dedup` option.

**Adaptive cap** — The maximum number of pages to scrape is computed from domain size:

| Unique paths | Default cap |
|-------------|-------------|
| <= 30 | All HTML snapshots |
| <= 200 | min(paths x 15, 10 000) |
| <= 1000 | min(paths x 8, 15 000) |
| > 1000 | 15 000 |

**Depth presets** scale the cap:

| Preset | Multiplier | Min/Max | Use case |
|--------|-----------|---------|----------|
| **Quick** | x 0.15 | min 200 | Fast overview, recent changes |
| **Standard** | x 1.0 | — | Balanced coverage (default) |
| **Full** | x 2.0 | max 30 000 | Maximum extraction depth |

---

## Interface walkthrough

### Config panel (post-preflight)

After preflight completes, the config panel appears with:

- **Snapshot count** — total HTML snapshots found, unique paths, date range
- **Date range** — optionally restrict the scan to a specific period
- **Depth preset** — quick / standard / full
- **Budget slider** — manually cap the page count
- **Category selector** — toggle which of the 10 extraction categories to run
- **Smart dedup** — when enabled (default), skips snapshots with identical CDX digest
- **Snapshot browser** — hierarchical tree of all discovered paths with per-path snapshot counts; check/uncheck individual snapshots for precise control (Advanced mode)

### Results tabs

Once the scan completes, results are organized across 10 tabs. Every tab shares the same controls:

- **Global search bar** — searches across ALL tabs simultaneously
- **Tab count** — shows `filtered/total` when a filter is active; tabs with matches are highlighted
- **Column sort** — click any column header to sort ascending/descending
- **Copy column** — one-click copy of all values in a column (e.g., all email addresses)
- **Export** — JSON (full results + metadata), CSV (current tab), All CSV (all categories in one file)

---

## Extraction categories

### Emails
Email addresses extracted from raw HTML (including obfuscated forms and mailto links). Noise-filtered: `noreply`, `no-reply`, `example`, image file extensions, and placeholder addresses are excluded automatically.

**Fields:** `value`, `first_seen`, `last_seen`, `occurrences`

---

### Phones
Phone numbers in international and local formats (E.164, US, French, UK, German...). Each match is validated: minimum 7 digits, maximum 15, not a date, not an IP, not a version number. Also extracts from `tel:` href links. Raw and normalized forms are both stored.

**Fields:** `raw`, `normalized`, `first_seen`, `last_seen`, `occurrences`

---

### Subdomains
Subdomains of the target domain found in links, scripts, iframes, and text. Useful for attack surface mapping: dev, staging, api, mail, cdn, and internal subdomains are often referenced from archived pages even after they're taken offline.

**Fields:** `value`, `first_seen`, `last_seen`, `occurrences`

---

### Endpoints
Internal URL paths discovered from `<a href>` links and `<form action>` attributes across all scraped pages. Each path is tracked with its first and last appearance, giving you a temporal map of the site's structure.

**Fields:** `path`, `first_seen`, `last_seen`, `occurrences`

---

### Trackers
Analytics and marketing tracker IDs embedded in the site:

| Tracker | Pattern |
|---------|---------|
| Google Analytics (Universal) | `UA-XXXXXXXX-X` |
| Google Analytics 4 | `G-XXXXXXXXXX` |
| Google Tag Manager | `GTM-XXXXXXX` |
| Google Ads | `AW-XXXXXXXXX` |
| Meta Pixel | `fbq(...)` |
| Hotjar | `hjid: XXXXXXX` |
| Mixpanel | `mixpanel.init("...")` |

Tracking ID changes over time indicate ownership transfers, rebranding, or third-party management of analytics.

**Fields:** `type`, `id`, `first_seen`, `last_seen`, `occurrences`

---

### Socials
Social media profile handles extracted from links. Detects: Twitter/X, LinkedIn (personal & company), Facebook, Instagram, Telegram, YouTube, GitHub, TikTok, Snapchat. Excludes share/intent links.

**Fields:** `platform`, `handle`, `url`, `first_seen`, `last_seen`, `occurrences`

---

### Persons
Individual names identified from:
- `<meta name="author">` and `<meta property="article:author">` tags
- JSON-LD structured data (`@type: Person`, `author`)
- HTML elements with author/byline/writer CSS classes

**Fields:** `name`, `context`, `first_seen`, `last_seen`, `occurrences`

---

### Tech Stack
Technology detection from multiple signals:
- `<meta name="generator">` and `<meta name="powered-by">` tags
- HTML comment signatures (`<!-- WordPress 6.2 -->`)
- CSS class indicators (`wp-content`, `drupal`, `joomla`)
- Script/link URLs matched against known framework patterns (React, Angular, Vue.js, Next.js, Nuxt, Svelte, Bootstrap, Tailwind, jQuery, D3.js, Lodash, Moment.js...)
- CDN references (Cloudflare, jsDelivr, unpkg, Google Fonts, Font Awesome)

Technology changes over time (`first_seen != last_seen`) are flagged in Key Findings.

**Fields:** `technology`, `version`, `first_seen`, `last_seen`, `occurrences`

---

### Cloud Buckets
Cloud storage URLs exposed in the page source:

| Provider | Pattern |
|----------|---------|
| Amazon S3 | `*.s3.amazonaws.com/*` |
| Google Cloud Storage | `storage.googleapis.com/*` |
| Azure Blob Storage | `*.blob.core.windows.net/*` |
| DigitalOcean Spaces | `*.digitaloceanspaces.com/*` |

Exposed bucket URLs can indicate misconfigured public access. These are always flagged as **CRITICAL** in Key Findings.

**Fields:** `value`, `first_seen`, `last_seen`, `occurrences`

---

### API Keys
Hardcoded credentials and API tokens found in page source:

| Type | Pattern |
|------|---------|
| AWS Access Key | `AKIA[0-9A-Z]{16}` |
| Google API Key | `AIza[0-9A-Za-z_-]{35}` |
| Stripe Secret/Public | `sk_live_...` / `pk_test_...` |
| Mailgun API Key | `key-[a-zA-Z0-9]{32}` |
| Twilio Auth Token | `SK[a-fA-F0-9]{32}` |
| SendGrid API Key | `SG.[...]{22}.[...]{43}` |
| Slack Webhook | `hooks.slack.com/services/T.../B...` |
| GitHub Token | `ghp_...` / `gho_...` / `ghs_...` / `ghu_...` / `ghr_...` |

These are always **CRITICAL** — test whether leaked keys are still active using the respective provider's API validation endpoint.

**Fields:** `type`, `value`, `first_seen`, `last_seen`, `occurrences`

---

## Key Findings & severity

WayTrace automatically generates prioritized findings from the extraction results. Findings are ranked in four severity tiers:

| Severity | Trigger | Action |
|----------|---------|--------|
| **CRITICAL** | API keys found, cloud buckets exposed | Test key validity, check bucket permissions |
| **HIGH** | Internal emails `@domain`, subdomains, sensitive endpoints (/api, /admin, /login, /auth, /dashboard, /internal, /staging, /debug, /graphql) | Search on HaveIBeenPwned, resolve with dig, probe endpoints |
| **MEDIUM** | Technology stack changes, analytics trackers (cross-domain correlation), persons identified | Check old versions for CVEs, cross-reference tracker IDs, search LinkedIn |
| **LOW** | Social profiles | Cross-reference handles across platforms |

CRITICAL and HIGH findings are always visible. MEDIUM and LOW findings are collapsed by default.

---

## Quick start

### Docker (recommended)

```bash
git clone https://github.com/HXLLO/WayTrace.git
cd WayTrace
cp .env.example .env
docker compose up -d
```

Open **http://localhost:8000** in your browser.

### Docker (development — hot reload)

```bash
cp .env.example .env
docker compose -f docker-compose.dev.yml up
```

### Manual

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env
uvicorn main:app --reload
```

Open **http://localhost:8000**.

---

## API reference

Interactive Swagger docs: **http://localhost:8000/docs**

### POST /api/scan/preflight

Lightweight CDX query — returns domain stats without scraping any pages.

```bash
curl -X POST http://localhost:8000/api/scan/preflight \
  -H "Content-Type: application/json" \
  -d '{"domain": "example.com"}'
```

```json
{
  "domain": "example.com",
  "total_snapshots": 47404,
  "html_snapshots": 12861,
  "unique_paths": 971,
  "unique_content": 8203,
  "date_range": { "first": "2003-08", "last": "2026-01" },
  "suggested_config": { "cap": 800 },
  "path_groups": [
    { "path": "/", "score": 2, "count": 412, "first": "20030801...", "last": "20260115...", "snapshots": [...] },
    { "path": "/contact", "score": 3, "count": 89, "first": "...", "last": "...", "snapshots": [...] }
  ]
}
```

---

### POST /api/scan

Create a full scan. Returns immediately with a `job_id`; poll or stream for results.

```bash
curl -X POST http://localhost:8000/api/scan \
  -H "Content-Type: application/json" \
  -d '{
    "domain": "example.com",
    "config": {
      "depth": "standard",
      "cap": 300,
      "date_from": "2018-01",
      "date_to": null,
      "categories": ["emails", "subdomains", "api_keys", "phones"],
      "smart_dedup": true
    }
  }'
```

`config` is optional — omit it entirely to use smart defaults.

```json
{ "job_id": "3f8a2c1d-..." }
```

**Advanced mode** — pass `selected_snapshots` (from preflight path_groups) to scrape exactly the pages you want:

```json
{
  "domain": "example.com",
  "selected_snapshots": [
    { "timestamp": "20210615120000", "url": "https://example.com/contact" }
  ]
}
```

**Valid categories:** `emails`, `subdomains`, `api_keys`, `cloud_buckets`, `analytics_trackers`, `endpoints`, `social_profiles`, `technologies`, `persons`, `phones`

---

### GET /api/jobs/{job_id}

Poll job status and retrieve results on completion.

```json
{
  "id": "3f8a2c1d-...",
  "status": "completed",
  "progress": 100,
  "step": "Scan complete",
  "meta": {
    "domain": "example.com",
    "total_snapshots_found": 12861,
    "snapshots_analyzed": 312,
    "pages_scraped": 298,
    "pages_failed": 14,
    "pages_deduped": 47,
    "date_first_seen": "2003-08",
    "date_last_seen": "2026-01",
    "scan_duration_seconds": 142
  },
  "results": {
    "highlights": [ { "severity": "HIGH", "category": "emails", ... } ],
    "emails": [ { "value": "ceo@example.com", "first_seen": "2009-03", "last_seen": "2021-11", "occurrences": 14 } ],
    "subdomains": [...],
    ...
  }
}
```

Status progression: `queued` -> `running` -> `completed` | `failed`

---

### GET /api/jobs/{job_id}/stream

Server-Sent Events stream for real-time progress updates. Preferred over polling.

```bash
curl -N http://localhost:8000/api/jobs/{job_id}/stream
```

```
event: progress
data: {"status": "running", "progress": 42, "step": "Scraping page 126/298"}

event: complete
data: {"status": "completed", "progress": 100, "meta": {...}, "results": {...}}
```

Events: `progress`, `complete`, `error`, `expired`. Heartbeat sent every 15s when idle.

---

### GET /api/health

```json
{ "status": "ok", "uptime_seconds": 3842, "active_jobs": 1 }
```

### GET /api/stats

```json
{ "total_scans_run": 42, "active_jobs": 1 }
```

---

## Configuration

All settings are controlled via environment variables in `.env` (copy from `.env.example`):

| Variable | Default | Range | Description |
|----------|---------|-------|-------------|
| `MAX_CONCURRENT_SCRAPES` | `30` | 1–50 | Parallel Wayback Machine requests |
| `ARCHIVE_REQUEST_TIMEOUT` | `30` | 5–120 | Per-request timeout in seconds |
| `ARCHIVE_RETRY_COUNT` | `3` | — | Retries on CDX/Wayback transient errors |
| `SCRAPE_DELAY_MIN` | `0.02` | — | Min delay between requests (seconds) |
| `SCRAPE_DELAY_MAX` | `0.08` | — | Max delay between requests (seconds) |
| `SCRAPE_MAX_RETRIES` | `3` | — | Retries per page scrape on transient errors |
| `JOB_TTL_SECONDS` | `7200` | — | Job expiry — auto-deleted after 2 hours |
| `MAX_ACTIVE_JOBS` | `10` | >= 1 | Maximum concurrent scans |
| `SCAN_TIMEOUT_SECONDS` | `3600` | — | Hard timeout per scan (60 minutes) |
| `PAGE_CACHE_MAX_MB` | `512` | — | Max page cache size in memory |
| `CDX_CACHE_TTL` | `300` | — | CDX cache lifetime (seconds) |
| `PAGE_CACHE_TTL` | `300` | — | Page cache lifetime (seconds) |
| `PRESCRAPE_LIMIT` | `15` | — | Max pages to pre-scrape during preflight |
| `COLLAPSE_THRESHOLD` | `250000` | — | CDX results threshold for month-collapse |
| `SCAN_RATE_LIMIT_RPM` | `10` | 0 = disabled | Scan requests/min per IP |
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:3000` | — | Comma-separated allowed origins |
| `LOG_LEVEL` | `INFO` | DEBUG/INFO/WARNING/ERROR | Logging verbosity |

---

## Architecture

```
backend/
├── main.py                   FastAPI app, CORS, lifespan (TTL cleanup loop)
├── config.py                 Pydantic settings loaded from .env
├── models.py                 All request/response schemas (Pydantic v2)
├── store.py                  In-memory job store, TTL expiry, concurrency lock
├── routers/
│   ├── scan.py               POST /scan, POST /scan/preflight, GET /jobs/{id}, SSE stream
│   └── health.py             GET /health, GET /stats
└── services/
    ├── cdx.py                CDX API client — HTML-only, paginated (resumeKey), gzip cache
    ├── filters.py            Smart snapshot selection — path scoring, dedup, depth presets
    ├── scraper.py            Concurrent Wayback downloader — semaphore, adaptive backoff
    └── extractor/
        ├── patterns.py       All regex patterns (email, phone, API keys, trackers, socials...)
        ├── extract.py        Per-page extraction — 10 categories, regex + selectolax DOM
        ├── finalize.py       extract_all() orchestration, accumulator -> sorted result lists
        ├── highlights.py     Severity ranking (CRITICAL/HIGH/MEDIUM/LOW)
        └── helpers.py        Utilities — normalize_phone, strip_wayback_artifacts...

frontend/
└── index.html                Single HTML file — vanilla JS, dark theme, no build step
                              Tabs, sortable columns, global search, CSV/JSON export

tests/
├── test_api.py               API validation, job lifecycle, category filtering
├── test_extractor.py         Regex patterns, extraction logic, highlights
└── test_filters.py           Snapshot selection, depth presets, date filtering, dedup
```

**Stack:** Python 3.12+, FastAPI, aiohttp, selectolax, Pydantic v2, loguru, httpx (testing)

**Key design decisions:**

- **No database** — all job state held in-memory; auto-expires via background TTL loop
- **Async throughout** — aiohttp for all network I/O, no blocking calls in async context
- **selectolax** over BeautifulSoup — C-based HTML parser, ~10x faster for high-volume parsing
- **CDX server-side filtering** — requests only `text/html` + `status:200`; avoids fetching thousands of image/CSS/JS entries
- **CDX file cache** — results cached as gzip-compressed JSON in `data/cdx/`; repeated queries hit disk instead of network
- **Content deduplication** — CDX SHA-1 digests collapse identical snapshots before scraping
- **Adaptive rate limiting** — asyncio.Semaphore + random per-request delay; auto-increases delay on 429s, gradually recovers on success
- **Domain deduplication** — submitting the same domain twice returns the existing job ID

---

## Tests

```bash
cd backend
python -m pytest tests/ -v          # all 90 tests
python -m pytest tests/test_extractor.py -v   # extraction patterns only
python -m pytest tests/test_filters.py -v     # snapshot selection only
python -m pytest tests/test_api.py -v         # API endpoints only
```

Coverage includes:
- API endpoint validation (domain format, category names, config bounds)
- Job lifecycle (queued -> running -> completed -> expired)
- Snapshot selection algorithm (scoring, depth presets, date filtering, deduplication)
- All 10 extraction categories (positive + false-positive test cases)
- Severity ranking logic (highlights generation)

---

## Legal & Ethics

WayTrace queries **only public archives** from the Wayback Machine (archive.org). It does not perform active scanning, port scanning, brute-forcing, DNS enumeration, or any intrusive action against target systems.

- Intended for legitimate security research, OSINT investigations, due diligence, and competitive intelligence
- Do not use for harassment, stalking, or any illegal activity
- Users are solely responsible for how they use the extracted data
- Respect archive.org's terms of service — do not flood requests or attempt to bypass rate limits

---

## License

[MIT](LICENSE)
