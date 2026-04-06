# Implement MarketDataProvider for Historical OHLCV

## Context

The history API endpoint (`/info/<symbol>/history`) currently returns hardcoded stub data. The goal is to wire it to real data via: abstract provider interface -> yfinance/akshare providers -> service layer (cache->DB->API) -> updated API endpoint. Only historical OHLCV — no live quote or intraday changes.

## Files to Create

| File | Purpose |
|---|---|
| `backend/info/market_data/__init__.py` | Package init (empty) |
| `backend/info/market_data/base.py` | `OHLCVBar` dataclass, `HistoricalProvider` ABC, `ProviderError` |
| `backend/info/market_data/providers/__init__.py` | Package init (empty) |
| `backend/info/market_data/providers/yfinance_provider.py` | `YFinanceProvider(HistoricalProvider)` — wraps `yfinance` for US ETFs |
| `backend/info/market_data/providers/akshare_provider.py` | `AkShareProvider(HistoricalProvider)` — wraps `akshare` for CN funds |
| `backend/info/market_data/registry.py` | `get_historical_chain()` — loads providers from settings, returns ordered list |
| `backend/info/market_data/service.py` | `HistoricalDataService` — `get_history()` (cache->DB->API), `backfill()` |
| `backend/info/management/__init__.py` | Package init |
| `backend/info/management/commands/__init__.py` | Package init |
| `backend/info/management/commands/backfill_ohlcv.py` | `python manage.py backfill_ohlcv KWEB --years=2` |

## Files to Modify

| File | Change |
|---|---|
| `backend/info/api.py` | Replace `_get_history` stub with `HistoricalDataService.get_history()`, add `range` param |
| `backend/config/settings.py` | Add `HISTORICAL_PROVIDERS`, `HISTORY_CACHE_TTL` |
| `backend/pyproject.toml` | Add `yfinance`, `akshare` dependencies |

## Not Touched (out of scope)

`tasks.py`, `views.py`, `celery.py`, `live.py`, `providers/sina.py`, `data_api.py` — all relate to live/intraday quotes, not historical data.

## Implementation Order

1. `base.py` — types and ABC
2. `__init__.py` files (market_data, providers, management)
3. `providers/yfinance_provider.py`
4. `providers/akshare_provider.py`
5. `registry.py`
6. `pyproject.toml` + `settings.py` — add deps and config
7. `service.py` — cache->DB->API orchestration
8. `api.py` — wire endpoint to service
9. `backfill_ohlcv.py` — management command
10. `uv sync` to install new deps

## Key Details

**`base.py`:**
- `OHLCVBar` dataclass: `date: date`, `open/high/low/close: Decimal | None`, `volume: int | None`
- `HistoricalProvider` ABC: `get_daily_ohlcv(symbol, start_date, end_date=None) -> list[OHLCVBar]`, `supports_symbol(symbol) -> bool`
- `ProviderError(Exception)`

**`yfinance_provider.py`:**
- `supports_symbol`: True if no `.SZ`/`.SH` suffix
- `get_daily_ohlcv`: `yfinance.Ticker(symbol).history(start=..., end=...)`, convert DataFrame to `list[OHLCVBar]`

**`akshare_provider.py`:**
- `supports_symbol`: True for `NNNNNN.SZ` / `NNNNNN.SH` patterns
- `get_daily_ohlcv`: use `ak.fund_etf_hist_sina()` or similar, normalize columns to `OHLCVBar`

**`registry.py`:**
- `get_historical_chain()`: reads `settings.HISTORICAL_PROVIDERS`, imports each class, returns `list[HistoricalProvider]`
- Cached with `@lru_cache`

**`service.py` — `get_history(fund_code, range_key)`:**
1. Redis check: `api:fund:{code}:history:{range}` -> HIT: return cached JSON
2. Compute date bounds from range_key (1M/3M/6M/1Y/all)
3. Query `FundDailyData.objects.filter(fund=fund, date__gte=start).order_by('date')`
4. If empty -> fetch via provider chain, bulk upsert to DB, re-query
5. Serialize to chart dicts, cache in Redis (24h TTL), return

**`service.py` — `backfill(fund_code, start_date, end_date)`:**
- Provider chain fetch + `bulk_create(update_conflicts=True)`
- Invalidate Redis cache keys

**`api.py` change:**
- `fund_history` reads `request.GET.get('range', '3M')`, calls `HistoricalDataService().get_history(symbol, range_key)`
- Delete `_get_history` stub

**Settings additions:**
```python
HISTORICAL_PROVIDERS = [
    'info.market_data.providers.yfinance_provider.YFinanceProvider',
    'info.market_data.providers.akshare_provider.AkShareProvider',
]
HISTORY_CACHE_TTL = 60 * 60 * 24
```

## Verification

1. `cd backend && uv sync` — deps install
2. `uv run python manage.py backfill_ohlcv KWEB --years=1` — populates DB
3. `uv run python manage.py runserver`, then `curl 'localhost:8000/info/KWEB/history?range=3M'` — returns real data
4. Second curl hit returns from Redis cache
