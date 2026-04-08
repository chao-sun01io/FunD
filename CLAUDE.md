# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FunD (Fun & Fund Data) is a Django web app for tracking financial fund data. It fetches live prices via Celery background tasks, caches data in Redis, and persists records in PostgreSQL.

## Development Workflows

### Hybrid (recommended for daily dev)

Infrastructure (PostgreSQL, Redis) runs in Docker; Django and Celery run as local processes.
Faster iteration, native debugger support, clean per-process logs.

```bash
# 1. One-time setup
cp backend/.env.local.example backend/.env
# fill in DJANGO_SECRET_KEY and POSTGRES_PASSWORD in backend/.env
cd backend && uv sync          # creates .venv and installs all deps incl. dev

# 2. Start infrastructure
docker compose -f docker-compose.infra.yml up -d

# 3. Apply migrations
uv run python manage.py migrate

# Terminal 1 — Django
DEBUG_LEVEL=DEBUG uv run python manage.py runserver

# Terminal 2 — Celery worker
uv run celery -A config worker --loglevel=info

# Terminal 3 — Celery beat (optional)
uv run celery -A config beat --loglevel=info
```

To run unit tests without any Docker (SQLite mode):
```bash
# In backend/.env, set USE_POSTGRES=False  (or comment it out)
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
docker compose -f docker-compose.prod.yml exec web python manage.py loaddata initial_data.json
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

## Architecture

Five Docker services: `web` (Django on port 8000), `celery` (worker), `celery-beat` (scheduler), `db` (PostgreSQL 13), `redis` (port 6380→6379).

**Request flow:** Browser → Django views → PostgreSQL (persistent fund data) + Redis (live price cache).

**Background data flow:** Celery Beat triggers `fetch_kweb_price` every 15 seconds → Celery worker fetches from Sina Finance API → stores in Redis under `info:<symbol>:latest`.

**Key files:**
- `backend/info/models.py` — `FundBasicInfo` and `FundDailyData` models
- `backend/info/views.py` — `index()` (fund list) and `detail()` (fund page with live price from Redis)
- `backend/info/tasks.py` — Celery tasks: `fetch_kweb_price`, `fetch_pcf_kweb`, `example_add`
- `backend/info/utils/redis_conn.py` — Redis connection pool (max 32 connections)
- `backend/info/market_data/data_api.py` — Sina Finance API wrapper
- `backend/config/celery.py` — Beat schedule and worker settings
- `backend/config/settings.py` — Redis caching backend, Celery config, DB settings

**Redis key schema** (see `doc/redis_db_design.md`):
- `info:<security_code>:latest` — live price hash
- `kweb_holdings_<date>` — PCF/holdings data
- `exchange_rate:usd2cny`, `exchange_rate:cny2hkd` — FX rates

## Environment

Three env templates:
- `backend/.env.local.example` — hybrid dev (local processes + Docker infra). Copy this for day-to-day work.
- `backend/.env.example` — full Docker (`docker-compose up`). `USE_POSTGRES=True`, service hostnames match Docker service names.
- `backend/.env.production.example` — production deployment (`docker-compose.prod.yml`). `DEBUG=False`, HTTPS, internal Redis port.

`USE_POSTGRES=True` → PostgreSQL; `False` or unset → SQLite (no Docker needed).

## Documentation

Design docs are in `doc/`: `backend.md`, `celery_tasks.md`, `redis_db_design.md`, `testing_strategy.md`.
