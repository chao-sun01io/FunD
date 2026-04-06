# Product Requirements: Fund Tracker

## Overview

Track ETFs and LOFs across US and CN A-share markets. Display fund details with historical charts, and (in later versions) cross-market premium/discount analysis and arbitrage trading tools.

**Motivating examples:**
- China Internet index: **KWEB** (US, USD) ↔ **164906.SZ** (CN, CNY)
- US Oil & Gas: **XOP** (US, USD) ↔ **162411.SZ** (CN, CNY)

---

## Architecture

### Market Data Source Abstraction

It provides multiple-resolution data:
- 1-minute intraday bars for the current trading day (for live charts)
- Daily OHLCV + NAV for historical charts and analysis
- Latest price and change for the info page (up to api provider's update frequency, e.g. every 15s for Sina Finance).

details in [market_data_layer.md](./market_data_layer.md)

### Storage

| Layer | What is stored | TTL / retention |
|---|---|---|
| PostgreSQL `FundDailyData` | OHLCV + NAV per fund per date | permanent |
| Redis `info:<code>:latest_quote` | Live quote (price, change, timestamp) | no TTL (overwritten every 15s) |
| Redis `api:fund:<code>:history:<range>` | Pre-serialised chart JSON | 24h TTL; invalidated on new DB write |

### Frontend Isolation

The frontend (templates + lightweight-charts) only consumes internal JSON API endpoints. It never calls external data APIs directly. This means:
- Live price widget → reads Redis via Django view context
- Historical charts → reads `/api/fund/<code>/history/?range=X`

---

## V1: Fund Detail Page

### Purpose
Each fund has its own page showing fund metadata, the latest live price, and interactive historical charts.

### User Stories
- As a user, I want to see a fund's key info and historical data on a single page.
- As a user, I want to see the latest price and daily change so I can quickly gauge how the fund is doing today.
- As a user, I want to see a price vs NAV chart so I can understand how the fund has historically traded relative to its intrinsic value.
- As a user, I want to see premium/discount % over time to identify patterns.
- As a user, I want to see trading volume alongside price to understand liquidity.

---

### Section 1: Historical Charts

Charts rendered client-side with **lightweight-charts v4** (TradingView, Apache 2.0), loaded from CDN. Data fetched from the internal history API endpoint.

#### Chart 1: Price vs NAV (line chart)
- Two lines: `closing_price` (market) and `net_asset_value` (NAV)
- Y-axis in native currency (USD for US funds)
- 

#### Chart 2: Premium / Discount % (baseline area chart)
- Single series: `(closing_price − net_asset_value) / net_asset_value × 100`
- Area fill: green when value > 0 (premium), red when < 0 (discount)
- Horizontal baseline at 0%
- Only rendered for dates where both closing_price and net_asset_value are non-null


#### Date Range Selector
Buttons: **1M · 3M · 6M · YTD · 1Y · All** — clicking refetches the API with the new range and re-renders all charts.

---

### Section 2: Fund Info & Live Quote

| Field | Source | Notes |
|---|---|---|
| Fund code, name, type | `FundBasicInfo` (DB) | |
| Listing exchange, currency | `FundBasicInfo` (DB) | |
| Management fee, inception date | `FundBasicInfo` (DB) | |
| Live price | Redis `info:<code>:latest_quote` | From Sina Finance, refreshed every 15s |
| Daily change (abs + %) | Redis | change_pct = change / (price − change) × 100 |
| Latest NAV | `FundDailyData.net_asset_value` (most recent DB row) | End-of-day; may be T-1 |
| Premium / Discount % | `(live_price − NAV) / NAV × 100%` | Computed in view |
| NAV date | `FundDailyData.date` | Shown alongside NAV so user knows if it's stale |

**Graceful degradation:**
- If Redis has no live quote → show last closing price from `FundDailyData` with a "Market closed" label
- If no NAV in DB → omit premium/discount field, show "NAV not available"

---

### History API Endpoint

```
GET /api/fund/<code>/history/?range=<range>
```

`range` values: `1M` (30d), `3M` (90d), `6M` (180d), `1Y` (365d), `all`

**Response:**
```json
[
  { "date": "2025-01-15", "price": 21.34, "nav": 21.20, "volume": 1234567 },
  ...
]
```

- `price` = `closing_price` (null → omitted from that row)
- `nav` = `net_asset_value` (null → omitted from that row)
- `volume` = null if not available (chart degrades gracefully)
- Rows sorted oldest-first (required by lightweight-charts)

**Caching:**
- Check Redis key `api:fund:<code>:history:<range>` first
- On miss: query `FundDailyData` filtered by date range, serialise, write to Redis with 24h TTL
- Celery's nightly `fetch_ohlcv` task writes to DB then deletes the affected cache keys

---

### URL
`/info/<fund_code>/` (existing URL, page enhanced)

---

### Data Ingestion (V1)

#### Live quotes (already working)
- Task: `fetch_kweb_price` every 15s → Sina Finance → Redis

#### Historical OHLCV (new)
- Task: `fetch_daily_ohlcv` — runs nightly at **23:00 ET** (after US market close + ETF NAV publication)
- Uses `YFinanceProvider.get_historical_ohlcv(symbol, start_date)` to fetch yesterday's OHLCV
- Upserts one row into `FundDailyData` (open, high, low, close, volume)
- NAV is **not** fetched automatically in V1 (see below)
- After DB write, deletes Redis cache keys for that fund (`api:fund:<code>:history:*`)

#### NAV data (V1 limitation)
US ETF end-of-day NAV is published by the fund company after close and is not freely available via a standard API. For V1:
- NAV is loaded manually via Django admin or a CSV import management command
- The `net_asset_value` field in `FundDailyData` stays null until populated
- Charts degrade gracefully: Chart 1 shows price-only line; Chart 2 is hidden

Automated NAV ingestion (e.g. scraping fund company pages or using a paid data provider) is deferred to a later version.

#### Initial backfill
Management command `python manage.py backfill_ohlcv <fund_code> [--years=2]` to load historical OHLCV on first setup.

---

## V2 Backlog: Peer Fund Dashboard

Cross-market premium/discount comparison for funds tracking the same index.

- Explicit `FundPeerGroup` model (ManyToMany to `FundBasicInfo`, with `is_reference` flag)
- Side-by-side table: live price, NAV, premium/discount %, daily change, forex-adjusted spread
- Only USD and CNY; forex rate = RMB/USD Central Parity Rate
- Auto-refresh every 15s
- URL: `/compare/<group_id>/`
- Requires: CN A-share live quote fetcher (Sina `sh`/`sz` prefix), historical OHLCV via Sina CN historical API or `akshare`, USD/CNY forex rate task, CN LOF NAV via Eastmoney / `akshare`

---

## V3 Backlog: Trading Helper (Order Book Comparison)

Level 2 order book view for two peer funds, surfacing arbitrage signals.

- 5-level bid/ask for each fund, annotated with premium/discount vs NAV
- Cross-fund signal: Buy1(A) vs Sell1(B) forex-adjusted spread + tradable qty
- Both directions shown; color-coded by actionability
- URL: `/trading-helper/<group_id>/?fund_a=<code>&fund_b=<code>`
- Requires: L2 order book data (Sina Finance does include 5-level order book for CN A-shares; US ETF L2 is not available via Sina)

---

## Model Changes (V1)

Add `volume` to `FundDailyData`:
```python
volume = models.BigIntegerField(null=True, blank=True)
```

---

## Out of Scope (all versions)
- HK-listed ETFs / HKD currency
- Automated trade execution
- Alerts / notifications on threshold breach
- LOF primary market subscription/redemption cost modeling
