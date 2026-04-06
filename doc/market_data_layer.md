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
    base.py                        # Dataclasses (OHLCVBar) + ABCs
    registry.py                    # Provider loading + fallback chain
    service.py                     # HistoricalDataService (Redis cache -> external API)
    providers/
        __init__.py
        yfinance_provider.py       # YFinanceProvider     (historical OHLCV, US)
        akshare_provider.py        # AkShareProvider      (historical OHLCV, CN)
    data_api.py                    # Legacy Sina wrapper for live quotes
```

### Abstract Interfaces (`base.py`)

**Data types:**

| Type | Fields | Purpose |
|---|---|---|
| `OHLCVBar` | `date, open, high, low, close, volume` | Standard exchange format between providers and service layer. `Decimal` for price fields. |
| `ProviderError` | exception | Raised on network/parse/rate-limit failures. |

**Abstract classes:**

| ABC | Methods | Implementors |
|---|---|---|
| `HistoricalProvider` | `get_daily_ohlcv(symbol, start_date, end_date) -> list[OHLCVBar]`; `supports_symbol(symbol) -> bool` | YFinanceProvider, AkShareProvider |

`supports_symbol` is a fast-path check — the fallback chain calls it before attempting a network request, so irrelevant providers are skipped without an HTTP round-trip.

### Concrete Providers

**YFinanceProvider** — wraps `yfinance` library. Converts pandas DataFrame rows to `OHLCVBar`. Normalizes timezone-aware timestamps to `date` objects.

**AkShareProvider** — wraps `akshare` library, using `fund_etf_hist_sina()`. Converts `NNNNNN.SZ`/`.SH` to Sina-style prefix (`sz164906`), fetches full history, then filters to the requested date range.

### Fallback Chain (`registry.py`)

Module-level function (cached with `@lru_cache`):
- `get_historical_chain() -> list[HistoricalProvider]` — reads `settings.HISTORICAL_PROVIDERS`, imports and instantiates each class

The chain execution pattern used by the service layer:

```
for provider in chain:
    if provider.supports_symbol(symbol):
        try:
            return provider.get_daily_ohlcv(...)
        except ProviderError:
            log warning, continue to next
raise ProviderError("All providers exhausted")
```

Ordering in settings encodes preference (primary first). This is a simple chain-of-responsibility — no need for per-symbol routing tables at this project's scale.

### Historical Data Service (`service.py`)

`HistoricalDataService` orchestrates a two-tier query flow: **Redis cache -> external API**.

**`get_history(fund_code, range_key) -> list[dict]`** — single entry point for the API endpoint:

```
1. Compute date bounds from range_key
       1M = 30d, 3M = 90d, 6M = 180d, YTD = Jan 1, 1Y = 365d, all = 1 year

2. Check Redis cache: api:fund:{symbol}:history:{start}:{end}
       HIT  -> return cached JSON
       MISS -> continue

3. Fetch from provider chain: fetch_from_chain(symbol, start_date, end_date)

4. Cache result in Redis with HISTORY_CACHE_TTL (default 24h), return
```

**Future enhancements:** PostgreSQL persistence (cache -> DB -> API three-tier flow) can be layered in when needed for offline access and backfill. The management command (`backfill_ohlcv`) is already in place for DB population when that tier is added.

### Configuration (`settings.py`)

```python
# Ordered fallback chain — first match wins
HISTORICAL_PROVIDERS = [
    'info.market_data.providers.yfinance_provider.YFinanceProvider',
    'info.market_data.providers.akshare_provider.AkShareProvider',
]
HISTORY_CACHE_TTL = 60 * 60 * 24    # 24 hours
```

## Backlog
- Add PostgreSQL persistence layer (cache -> DB -> API three-tier flow)
- Add support for more data sources
- Live quote abstraction: `LiveQuoteProvider` ABC + `SinaFinanceProvider` (migrate from `data_api.py`), with `LiveQuote` dataclass (`symbol, price, change, timestamp, extra: dict`)
- Intraday abstraction (`live.py`): `IntradaySource` ABC with `PollingIntradaySource` (Celery Beat) and `WebSocketIntradaySource` (future). Both converge on the same Redis state — `latest()` always reads from Redis, the difference is only how data gets into Redis (Celery task = write side, IntradaySource = read side)
- If the volume grows significantly we can consider using a time-series database like TimescaleDB for better performance and advanced features
- Frontend: WebSocket feed for real-time updates without page refresh