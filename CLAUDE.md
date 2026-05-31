# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FunD (Fun & Fund Data) is a Django web app for tracking financial fund data. It fetches live prices via Celery background tasks, caches data in Redis, and persists records in PostgreSQL.

## Development Workflows

### Hybrid (recommended for daily dev)

Only Redis runs in Docker. Django runs in its own terminal so `runserver`'s
autoreload + tracebacks stay front-and-center; Celery worker + Beat run together
via [honcho](https://github.com/nickstenning/honcho), driven by `backend/Procfile`.
Database defaults to SQLite — no Postgres container needed.

```bash
# 1. One-time setup
cp backend/.env.local.example backend/.env
# fill in DJANGO_SECRET_KEY in backend/.env
cd backend && uv sync          # creates .venv and installs all deps incl. dev (honcho)

# 2. Start Redis (only infra service needed)
docker compose -f docker-compose.infra.yml up -d

# 3. Apply migrations (creates SQLite db on first run)
uv run python manage.py migrate

# 4. Terminal A — Django
LOG_LEVEL=DEBUG uv run python manage.py runserver

# 5. Terminal B — Celery worker + Beat together
uv run honcho start
```

Honcho logs are interleaved with `worker | …`, `beat | …` prefixes; Ctrl-C stops both.

Run a single Celery process when debugging: `uv run honcho start worker` (or invoke the underlying
command directly).

> **Caveat:** honcho does not auto-restart Celery on code edits. After changing task code, Ctrl-C
> and rerun `honcho start`. Django auto-reloads as normal in its own terminal.

To run unit tests without any Docker (SQLite is already the default):
```bash
cd backend && uv run pytest
```

### Full Docker (for integration checks or onboarding)

All five services (web, celery, celery-beat, db, redis) in containers.

```bash
cp backend/.env.example backend/.env
# fill in DJANGO_SECRET_KEY and POSTGRES_PASSWORD

docker-compose up        # foreground
docker-compose up -d     # detached
```

### Production Deployment

See `doc/deployment.md` for full instructions. Quick reference:

```bash
cp backend/.env.production.example backend/.env
# fill in all required values (secret key, password, domain)
./scripts/init-letsencrypt.sh your@email.com
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec web python manage.py migrate
docker compose -f docker-compose.prod.yml exec web python manage.py loaddata initial_funds.json
```

### Common commands (run from `backend/`)

```bash
uv run python manage.py makemigrations info
uv run python manage.py migrate
uv run pytest

# Add a new dependency
uv add <package>

# Add a dev-only dependency
uv add --dev <package>
```

### Commit rules

-  Think whether to commit current changes before switching to a different or less related topic.

## Architecture

Five Docker services: `web` (Django on port 8000), `celery` (worker), `celery-beat` (scheduler), `db` (PostgreSQL 17), `redis` (port 6380→6379).

**Request flow:** Browser → Django views → PostgreSQL (persistent fund data) + Redis (live price cache).

**Background data flow:** Celery Beat triggers `poll_live_quotes` every 15 seconds → worker fetches the symbols listed in `settings.INTRADAY_SYMBOLS` (default `['KWEB']`) from Sina US → writes the latest tick to `tick:<symbol>:latest` and updates the current 1-min OHLCV bar in `price:<symbol>:1m:<date>`.

**Key files:**
- `backend/info/models.py` — `FundBasicInfo` and `FundDailyData` models
- `backend/info/views.py` — `index()` (fund list) and `detail()` (fund page with live tick from Redis)
- `backend/info/tasks.py` — Celery tasks (currently `poll_live_quotes`)
- `backend/info/utils/redis_conn.py` — Redis connection pool (max 32 connections)
- `backend/info/market_data/` — three-tier market data layer (providers → registry → service → persistence); see `doc/market_data_layer.md`
- `backend/config/celery.py` — Beat schedule and worker settings
- `backend/config/settings.py` — Redis caching backend, Celery config, DB settings

**Redis keys written by the code today** (the broader planned schema lives in `doc/redis_db_design.md`):
- `tick:<symbol>:latest` — latest tick JSON (price/volume/OHL/ts), 24h TTL
- `price:<symbol>:1m:<YYYY-MM-DD>` — hash of `HH:MM` → 1-min OHLCV bar JSON, 48h TTL

## Environment

Three env templates:
- `backend/.env.local.example` — hybrid dev (local processes + Docker infra). Copy this for day-to-day work.
- `backend/.env.example` — full Docker (`docker-compose up`). `USE_POSTGRES=True`, service hostnames match Docker service names.
- `backend/.env.production.example` — production deployment (`docker-compose.prod.yml`). `DEBUG=False`, HTTPS, internal Redis port.

`USE_POSTGRES=True` → PostgreSQL; `False` or unset → SQLite (no Docker needed).

## Documentation

 - Design docs are in `doc/`: `backend.md`, `celery_tasks.md`, `redis_db_design.md`, `market_data_layer.md`, `db_tables.md`, `testing_strategy.md`, `deployment.md`, `site_admin.md`, `django-cmd-bank.md`, `board.md`, `product_requirements.md`.
 - When adding a new Django management command, also document it in `doc/site_admin.md`.
 - For non-trivial changes, update the docs as well.
