# TRD: OSINT Ingestion, Dedup & Dashboard v1

Project Inception — Threat Intelligence Platform
Translates: `docs/product/PRD-ingestion-dedup-dashboard-v1.pdf`
Status: Draft v1 | Owner: CTO

## 1. Architecture

Four deployable pieces, no containers required in production:

| Component | Host | Notes |
|---|---|---|
| Frontend (React + Vite + TS) | Render Static Site | Free, unlimited, no spin-down |
| API + ingestion trigger (FastAPI) | Render Web Service | 750 free hrs/mo; spins down after 15 min idle (~1 min cold start on wake) |
| Postgres | Supabase free project | 500 MB storage; pauses (not deletes) after 7 days with zero API traffic |
| Scheduler | GitHub Actions (`cron:` workflow) | Calls the API's protected ingest endpoint on a recurring schedule |

Local development: Python venv + Node dev server + either a local Postgres install or a
second free Supabase project — Docker Compose is optional here, not required, and can be
added later purely for dev convenience.

Why this shape: Render's free tier has no background-worker or cron-job service type, so
the "recurring, unattended" requirement (FR2) is satisfied by an external free scheduler
(GitHub Actions) calling into the API rather than an in-process scheduler running inside a
long-lived worker container. Supabase was chosen over Render's own free Postgres because
Render's free database is hard-deleted ~44 days after creation; Supabase's free project
only pauses on inactivity and is trivially kept warm by the daily ingestion schedule itself.

## 2. Data Model

```sql
CREATE TYPE indicator_type AS ENUM ('ip', 'domain', 'url', 'hash', 'cve');

CREATE TABLE canonical_indicators (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    indicator_type    indicator_type NOT NULL,
    value_normalized  TEXT NOT NULL,
    value_raw         TEXT NOT NULL,
    dedup_key         TEXT NOT NULL UNIQUE,
    first_seen        TIMESTAMPTZ NOT NULL,
    last_seen         TIMESTAMPTZ NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_canonical_type ON canonical_indicators(indicator_type);
CREATE INDEX idx_canonical_last_seen ON canonical_indicators(last_seen);

-- One row per (indicator, source) contribution. This *is* the FR8 audit trail:
-- two records share a dedup_key -> this table shows exactly which sources and when.
CREATE TABLE indicator_sources (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    indicator_id       UUID NOT NULL REFERENCES canonical_indicators(id) ON DELETE CASCADE,
    source_name        TEXT NOT NULL,
    source_first_seen  TIMESTAMPTZ NOT NULL,
    source_last_seen   TIMESTAMPTZ NOT NULL,
    raw_metadata       JSONB,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (indicator_id, source_name)
);
CREATE INDEX idx_sources_indicator ON indicator_sources(indicator_id);
CREATE INDEX idx_sources_name ON indicator_sources(source_name);

-- FR3 / FR12: per-run log backing the ingestion health widget.
CREATE TABLE ingestion_runs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_name   TEXT NOT NULL,
    started_at    TIMESTAMPTZ NOT NULL,
    finished_at   TIMESTAMPTZ,
    status        TEXT NOT NULL CHECK (status IN ('running','success','failed','partial')),
    record_count  INTEGER,
    error_detail  TEXT
);
CREATE INDEX idx_runs_source ON ingestion_runs(source_name, started_at DESC);

-- FR6: malformed records are rejected from canonical storage but kept here for traceability.
CREATE TABLE rejected_records (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id        UUID REFERENCES ingestion_runs(id) ON DELETE SET NULL,
    source_name   TEXT NOT NULL,
    raw_value     TEXT,
    reason        TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**500 MB budget note:** `indicator_sources.raw_metadata` grows faster than the canonical
table (one row per source per indicator). Cap what gets stored there to the fields actually
useful for the detail view (FR13) rather than the full raw API payload, and consider a
retention job that prunes `rejected_records` and stale `ingestion_runs` after ~90 days.

## 3. Normalization & Dedup

Deterministic, exact-match only (FR8 rules out fuzzy matching — it can't be audited with a
one-line answer, which real-world dedup logic needs to survive scrutiny).

| Type | Normalization | Dedup key input |
|---|---|---|
| IP | Canonical IPv4/IPv6 form (via stdlib `ipaddress`) | type + canonical IP |
| Domain | Lowercase, strip trailing dot, strip leading `www.`? *(decide during build — flag if ambiguous)* | type + normalized domain |
| URL | Lowercase scheme/host, strip default port, keep path/query as-is | type + normalized URL |
| Hash | Lowercase; distinguish MD5/SHA1/SHA256 by length | type + hash |
| CVE | Uppercase `CVE-YYYY-NNNNN` form | type + CVE ID |

`dedup_key = sha256(indicator_type + "|" + normalized_value)`. Ingestion upserts by this
key: new key → insert canonical row; existing key → append/update the matching
`indicator_sources` row, bump `last_seen`.

## 4. API Contract (FastAPI)

| Endpoint | Purpose |
|---|---|
| `GET /api/indicators` | Paginated, filterable list (type, source, date range, free-text) — FR10 |
| `GET /api/indicators/{id}` | Detail view: contributing sources + raw metadata — FR13 |
| `GET /api/indicators/export?format=csv\|json&...` | Export current filtered set — FR14, defanged by default with a `raw=true` override |
| `GET /api/sources` | Per-source health: last run time/status — FR12 |
| `GET /api/sources/{name}/volume` | Time series for the volume chart — FR11 |
| `POST /internal/ingest/{source}` | Triggers one source's ingestion; requires `X-Ingest-Secret` header matching a server-side env var; called by the GitHub Actions cron |
| `GET /health` | Liveness check |

## 5. Threat Model (STRIDE)

STRIDE is a checklist for thinking through what can go wrong with a system, one letter per
failure mode. Applied to this service:

- **Spoofing** — `/internal/ingest/{source}` must not be publicly triggerable; anyone who
  found the URL could spam it or skew ingestion counts. Mitigation: shared-secret header,
  checked against an env var never committed to the repo.
- **Tampering** — v1 is read-only + export for the dashboard user, so there's no exposed
  write path beyond the ingest endpoint above. Real risk is a leaked Supabase service key
  giving direct DB write access — keep it in Render's env var store, never in code.
- **Repudiation** — `ingestion_runs` gives an audit trail of every run (source, time,
  outcome, count), which is the accountability FR3 already asks for. No per-user
  repudiation concern since this is explicitly single-user (non-goal: no auth/RBAC).
- **Information Disclosure** — the biggest realistic risk isn't the IOC data itself (it's
  public OSINT), it's credential leakage: Supabase connection string, OTX/abuse.ch keys,
  and the ingest shared secret all need to live in environment variables, not in the repo
  or in error messages returned to the client.
- **Denial of Service** — Render's free compute is 0.1 CPU / 512 MB. A public dashboard or
  a repeatedly-hit `/internal/ingest` endpoint could exhaust that. Mitigation: the secret
  header on the ingest endpoint (also blocks casual DoS), and basic rate limiting on the
  public read API if this ever gets a public link shared around.
- **Elevation of Privilege** — no privilege tiers exist in v1 (explicit non-goal), so
  nothing to elevate yet. Re-open this analysis when RBAC lands in a later phase.

## 6. Non-Functional Requirements — how each is met

- **Reliability** (per-source isolation): each source's ingestion runs as an independent
  call to `/internal/ingest/{source}`; one failing does not block another's scheduled call.
- **Data integrity**: every run writes to `ingestion_runs` regardless of outcome — failures
  are visible in the health widget, never silently dropped.
- **Performance** (~100k indicators): covered by indexes on `indicator_type`, `last_seen`,
  and the FK on `indicator_sources`; revisit only if the dashboard measurably lags.
- **Safety** (defanging): raw values stored as-is; defanging applied at the API/render layer
  only, with an explicit `raw=true` opt-out on export for analysts feeding it elsewhere.
- **Portability**: no required cloud dependency to *run* the code — Render/Supabase are a
  deployment choice, not a hard dependency; the same FastAPI + Postgres app runs locally.

## 7. Task Breakdown

- **M0 — Accounts & environment** (see prerequisite checklist below)
- **M1 — Data layer**: Supabase project, schema via Alembic migration, connection from FastAPI
- **M2 — Ingestion**: one client module per source (OTX, URLhaus, ThreatFox, CISA KEV), shared normalization + dedup logic, `ingestion_runs`/`rejected_records` logging
- **M3 — API layer**: list/detail/export/sources endpoints, defanging logic
- **M4 — Scheduler**: `/internal/ingest/{source}` endpoint + GitHub Actions cron workflow
- **M5 — Frontend**: indicator table (search/filter), volume chart, health widget, detail view
- **M6 — Deploy**: Render static site + web service wired to Supabase, all secrets set as env vars
- **M7 — Validate**: confirm success metrics from the PRD (≥95% scheduled-run success over 2 weeks, dedup rate is quotable, full live demo path works end-to-end)

## 8. Prerequisites Before Building

**Accounts (you create/hold these — I never see or handle credentials):**
- [ ] GitHub — already have the repo; needed for GitHub Actions
- [ ] AlienVault OTX account → API key (Settings page)
- [ ] abuse.ch account → Auth-Key at auth.abuse.ch (covers both URLhaus + ThreatFox)
- [ ] Supabase account → free project created
- [ ] Render account → connected to this GitHub repo

**No account needed:** CISA KEV feed is public, unauthenticated JSON.

**Secrets to generate once accounts exist:**
- [ ] A random `INGEST_SHARED_SECRET` string (for GitHub Actions → Render endpoint auth) — generate with e.g. `openssl rand -hex 32`
- [ ] Supabase database connection string (from the Supabase project settings)

**Local tooling:**
- [ ] Python 3.11+
- [ ] Node.js 20+
- [ ] `git` (already set up)
- [ ] Docker — optional, only if you want containerized local dev

## 9. Open Decisions Deferred to Build Time

- Exact domain normalization edge cases (e.g., strip `www.`?) — will resolve against real
  sample data from the three sources rather than guessing upfront.
- Whether `indicator_sources.raw_metadata` gets a size cap or field allowlist per source.
