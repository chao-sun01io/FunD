## Requirements for Market Data Layer

It provides a unified interface for fetching both live and historical market data, abstracting away the underlying data sources and formats. 

- Data Pipelines: Push style and Pull style. 
- Hybrid data source. All external API calls go through a provider interface so the underlying source can be swapped without touching tasks or views.
- Multiple resolutions (1-min intraday + daily OHLCV)
- Storage and caching 

### Use cases
- get fund metadata (name, type, currency, etc.) for display on the info page
- get the historical OHLCV/NAV data
- show latest price and change on the info page. It requires frontend refresh to fetch the latest price.
- build a database for analysis and backtesting of trading strategies (e.g. premium/discount patterns, mean reversion, etc.). 
- Trading signals: it requires real-time price updates, and using streaming APIs or WebSocket feeds from data providers. 
- It supports multiple data sources (e.g. Yahoo Finance, Sina Finance, AkShares etc.) and can be extended to add more sources in the future.


## Design

The application layer accesses the market data layer through a unified provider interface. The provider abstracts away the details of fetching and processing data from different sources, and provides a consistent API for the application layer to consume.

### Module Structure

```
info/market_data/
    __init__.py
    base.py                        # Dataclasses (OHLCVBar, NAVPoint) + ABCs
    registry.py                    # Provider loading + fallback chain
    service.py                     # HistoricalDataService (Redis → DB → providers)
    persistence.py                 # DB read/write (load_bars_from_db, persist_bars)
    providers/
        __init__.py
        yfinance_provider.py       # YFinanceProvider          (OHLCV, US; nav=close)
        akshare_provider.py        # AkShareProvider           (OHLCV, CN)
        eastmoney_nav_provider.py  # EastMoneyNAVProvider      (NAV, CN only)
    data_api.py                    # Legacy Sina wrapper for live quotes
```

### Abstract Interfaces (`base.py`)

**Data types:**

| Type | Fields | Purpose |
|---|---|---|
| `OHLCVBar` | `date, open, high, low, close, volume, nav` | Standard exchange format between providers and service layer. `Decimal` for price fields. `nav` is optional. |
| `NAVPoint` | `date, nav` | Official unit NAV for a fund. |
| `ProviderError` | exception | Raised on network/parse/rate-limit failures. |

**Abstract classes:**

| ABC | Methods | Implementors |
|---|---|---|
| `HistoricalProvider` | `get_daily_ohlcv(symbol, start_date, end_date) -> list[OHLCVBar]`; `supports_symbol(symbol) -> bool` | YFinanceProvider, AkShareProvider |
| `NAVProvider` | `get_daily_nav(symbol, start_date, end_date) -> list[NAVPoint]`; `supports_symbol(symbol) -> bool` | EastMoneyNAVProvider |

`supports_symbol` is a fast-path check — the fallback chain calls it before attempting a network request, so irrelevant providers are skipped without an HTTP round-trip.

### Concrete Providers

**YFinanceProvider** — wraps `yfinance` library. Converts pandas DataFrame rows to `OHLCVBar`. Normalizes timezone-aware timestamps to `date` objects. For US-listed ETFs, sets `nav = close` because Yahoo Finance does not provide historical NAV — the close price closely tracks NAV for liquid US ETFs.

**AkShareProvider** — wraps `akshare` library, using `fund_etf_hist_sina()`. Converts `NNNNNN.SZ`/`.SH` to Sina-style prefix (`sz164906`), fetches full history, then filters to the requested date range.

**EastMoneyNAVProvider** — fetches official unit NAV from fund.eastmoney.com for CN exchange-listed funds/ETFs (`.SZ`, `.SH`, `.BJ` symbols only). Does not support US-listed symbols.

### Fallback Chain (`registry.py`)

Module-level functions (cached with `@lru_cache`):
- `get_historical_chain() -> list[HistoricalProvider]` — reads `settings.HISTORICAL_PROVIDERS`
- `get_nav_chain() -> list[NAVProvider]` — reads `settings.NAV_PROVIDERS`

The chain execution pattern used by the service layer:

```
for provider in chain:
    if provider.supports_symbol(symbol):
        try:
            return provider.get_daily_ohlcv(...)  # or get_daily_nav(...)
        except ProviderError:
            log warning, continue to next
raise ProviderError("All providers exhausted")
```

Ordering in settings encodes preference (primary first). This is a simple chain-of-responsibility — no need for per-symbol routing tables at this project's scale.

**NAV resolution strategy:** The service first fetches OHLCV. If the OHLCV bars already carry NAV (e.g. YFinance sets `nav=close` for US ETFs), the separate NAV chain is skipped entirely. Otherwise, it fetches from the NAV chain and merges by date.

### Historical Data Service (`service.py`)

`HistoricalDataService` orchestrates a three-tier query flow: **Redis response cache → DB → provider gap-fill**.

**`get_history(fund_code, range_key) -> list[dict]`** — single entry point for the API endpoint:

```
1. Compute date bounds from range_key
       1M = 30d, 3M = 90d, 6M = 180d, YTD = Jan 1, 1Y = 365d, all = 1 year

2. Redis response cache: api:fund:{symbol}:history:{version}:{start}:{end}
       HIT  -> return cached JSON
       MISS -> continue

3. DB read: load existing bars from FundDailyData

4. Gap computation: identify missing date ranges
       - Front gap: [start, db_min-1] if DB starts later (always filled)
       - Back gap: [db_max+1, end] if DB ends earlier (gated by freshness TTL)
       - Interior gaps: dates with NULL fields, collapsed into ranges (gated)

5. For each gap: fetch OHLCV + NAV from providers, persist to DB

6. Re-read DB, serialize, cache in Redis with HISTORY_CACHE_TTL (default 24h)
```

A per-symbol freshness stamp (`mktdata:{symbol}:last_check_at`, 1h TTL) gates back-gap and interior-gap fetches to avoid hammering providers when they simply don't have the data.

### Configuration (`settings.py`)

```python
# Ordered fallback chain — first match wins
HISTORICAL_PROVIDERS = [
    'info.market_data.providers.yfinance_provider.YFinanceProvider',
    'info.market_data.providers.akshare_provider.AkShareProvider',
]
NAV_PROVIDERS = [
    'info.market_data.providers.eastmoney_nav_provider.EastMoneyNAVProvider',
]
HISTORY_CACHE_TTL = 60 * 60 * 24    # 24 hours
```

## Backlog
- Add support for more data sources
- Live quote abstraction: `LiveQuoteProvider` ABC + `SinaFinanceProvider` (migrate from `data_api.py`), with `LiveQuote` dataclass (`symbol, price, change, timestamp, extra: dict`)
- Intraday abstraction (`live.py`): `IntradaySource` ABC with `PollingIntradaySource` (Celery Beat) and `WebSocketIntradaySource` (future). Both converge on the same Redis state — `latest()` always reads from Redis, the difference is only how data gets into Redis (Celery task = write side, IntradaySource = read side)
- If the volume grows significantly we can consider using a time-series database like TimescaleDB for better performance and advanced features
- Frontend: WebSocket feed for real-time updates without page refresh