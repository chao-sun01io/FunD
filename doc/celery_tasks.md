It uses celery as a task queue to handle background tasks in a Django application.

# Tasks

## `poll_live_quotes` (every 15 seconds)

Polls Sina Finance for all symbols in `settings.INTRADAY_SYMBOLS`. For each symbol:
1. Fetches latest quote (price, volume, open, high, low)
2. Buffers the tick in Redis (`tick:{symbol}:latest`)
3. Aggregates into 1-min bars in Redis hash (`price:{symbol}:1m:{date}`)

This powers the intraday (1D) chart and the "Latest Price" card on the detail page.

## Planned tasks (not yet implemented)

- Get PCF data on a daily basis
- Get fund basic data when market is closed, update `info_fundbasicinfo`
- For US listed funds, get nightly data from the US market

# How to run

```bash
# Start Redis (the only infra service needed for hybrid dev)
docker compose -f docker-compose.infra.yml up -d

# Terminal A — Django
cd backend && uv run python manage.py runserver

# Terminal B — Celery worker + Beat together via honcho (backend/Procfile)
cd backend && uv run honcho start
```

Both worker and beat must be running for intraday data collection to work. The beat scheduler triggers `poll_live_quotes` every 15 seconds; the worker executes it. `honcho start` launches both and stops them together on Ctrl-C. Django runs in its own terminal so `runserver`'s autoreload and tracebacks remain visible.

To run a single Celery process standalone (e.g. when attaching a debugger), the underlying commands still work:

```bash
uv run celery -A config worker --loglevel=info
uv run celery -A config beat   --loglevel=info
```

# Scheduler

Beat schedule is defined in `config/celery.py`. Future: migrate to `django-celery-beat` for DB-managed schedules.
