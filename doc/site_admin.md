# Site Administration

Management commands for operating and maintaining the FunD application.

## Data Management

### `backfill_ohlcv`

Bulk-fetch historical OHLCV data for a fund and persist to the database.

```bash
uv run python manage.py backfill_ohlcv KWEB              # default 2 years
uv run python manage.py backfill_ohlcv 164906.SZ --years=5
uv run python manage.py backfill_ohlcv KWEB --start-date=2023-01-01
```

### `fill_missing`

Find `FundDailyData` rows with NULL fields (open/high/low/close/volume/nav) and attempt to fill them from providers. Uses `persist_bars` which only fills NULL fields — never overwrites existing data.

```bash
# Dry run — report missing data without fetching
uv run python manage.py fill_missing --dry-run

# Dry run for a specific fund
uv run python manage.py fill_missing KWEB --dry-run

# Only check specific fields (comma-separated: open,high,low,close,volume,nav)
uv run python manage.py fill_missing KWEB --dry-run --fields=nav,close

# Fill gaps for a specific fund
uv run python manage.py fill_missing KWEB

# Fill all funds
uv run python manage.py fill_missing
```

**Behavior:**
- Groups missing dates into contiguous ranges (5-day gap tolerance to bridge weekends) to minimize provider calls
- Reports per-field NULL counts in dry-run mode
- Tracks how many NULL fields were actually filled vs. what providers couldn't supply

## Cache

### `clear_cache`

Flush all keys from the Redis cache (live prices, response cache, freshness markers, etc.). Prompts for confirmation unless `--yes` is passed.

```bash
uv run python manage.py clear_cache        # interactive confirmation
uv run python manage.py clear_cache --yes  # skip confirmation
```

## Celery

### `trigger_celery_task`

Manually trigger Celery tasks (PCF fetch + live price fetch) for testing.

```bash
uv run python manage.py trigger_celery_task
```

## Data Sources

### `sina_quote`

Probe `get_quotes_from_sina_us` directly from the CLI — useful for checking whether
the upstream is reachable, what fields it returns, and whether a symbol is supported.

```bash
uv run python manage.py sina_quote KWEB AAPL          # formatted table
uv run python manage.py sina_quote KWEB --json        # raw JSON
```
