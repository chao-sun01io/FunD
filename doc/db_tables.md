# Database & Storage Design

## Current Tables (from `backend/info/models.py`)

### `info_fundbasicinfo`

Stores static metadata about each tracked fund.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `fund_id` | integer | PK, auto | |
| `fund_code` | varchar(20) | unique, not null | e.g. `KWEB`, `164906.SZ` |
| `fund_name` | varchar(200) | not null | |
| `fund_type` | varchar(50) | not null | e.g. `ETF`, `LOF` |
| `currency` | varchar(10) | not null, default `CNY` | `USD` or `CNY` |
| `listing_exchange` | varchar(100) | not null | e.g. `NASDAQ`, `SZ` |
| `fund_company` | varchar(100) | not null | |
| `inception_date` | date | not null | |
| `index_tracked` | varchar(200) | nullable | e.g. `CSI China Internet Index` |
| `management_fee` | decimal(5,4) | nullable | annual rate |
| `custodian_fee` | decimal(5,4) | nullable | annual rate |

---

### `info_funddailydata`

Stores end-of-day OHLCV + NAV per fund per date. One row per (fund, date).

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | bigint | PK, auto | |
| `fund_id` | integer | FK → `info_fundbasicinfo`, CASCADE | |
| `date` | date | not null | trading date |
| `opening_price` | decimal(10,4) | nullable | |
| `closing_price` | decimal(10,4) | nullable | |
| `highest_price` | decimal(10,4) | nullable | |
| `lowest_price` | decimal(10,4) | nullable | |
| `net_asset_value` | decimal(15,4) | nullable | official end-of-day NAV |
| `estimated_nav` | decimal(15,4) | nullable | intraday estimated NAV (iNAV) |
| `trading_volume` | bigint | nullable | **to be uncommented** |

**Constraints:** `UNIQUE (fund_id, date)` · `ORDER BY date DESC`

---

## Multi-Resolution Price Storage

Different resolutions serve different use cases:

| Resolution | Use case | Data source | Retention | Storage |
|---|---|---|---|---|
| 1-minute bar | Intraday chart for today | Sina Finance (live, every 1 min) | Current trading day + N days archive | Redis (live day) + PostgreSQL (short-term) |
| Daily OHLCV | Historical charts (1M / 3M / 1Y / All) | Yahoo Finance / yfinance (nightly) | Permanent | PostgreSQL `info_funddailydata` |

The two resolutions are **independent pipelines** — daily data is fetched directly from an external API and is not derived from 1-minute bars.

---

### Resolution 1: 1-Minute Intraday Bars

Stores OHLCV bars for the current trading day. Data is fetched by a Celery task running every minute during market hours.

**Redis (primary, live day only):**

Key: `price:<fund_code>:1m:<YYYY-MM-DD>` → Hash of `<HH:MM>` → JSON bar

```
price:KWEB:1m:2025-03-28
  "09:30" → {"o": 21.10, "h": 21.18, "l": 21.08, "c": 21.15, "v": 45200}
  "09:31" → {"o": 21.15, "h": 21.22, "l": 21.13, "c": 21.20, "v": 38100}
  ...
```

TTL: expires 2 hours after market close (e.g. 18:00 ET for US, 17:00 CST for CN).

**PostgreSQL (optional, short-term archive):**

Proposed new table `info_fundintraday1min` — stores the last N trading days of 1-minute bars for replay and debugging. Rows older than the retention window are deleted by a nightly cleanup task.

```python
class FundIntraday1Min(models.Model):
    fund        = ForeignKey(FundBasicInfo, on_delete=CASCADE)
    timestamp   = DateTimeField()          # timezone-aware; e.g. 2025-03-28 09:30:00-04:00
    open        = DecimalField(max_digits=10, decimal_places=4)
    high        = DecimalField(max_digits=10, decimal_places=4)
    low         = DecimalField(max_digits=10, decimal_places=4)
    close       = DecimalField(max_digits=10, decimal_places=4)
    volume      = BigIntegerField(null=True, blank=True)

    class Meta:
        unique_together = ('fund', 'timestamp')
        indexes = [Index(fields=['fund', 'timestamp'])]
```

Retention: configurable via `INTRADAY_RETENTION_DAYS` (default: 5 trading days).

---

### Resolution 2: Daily OHLCV

Uses the existing `info_funddailydata` table. One row per (fund, date), permanent.

**Pending model change:** uncomment `trading_volume` and rename to `volume` for clarity, or keep as `trading_volume` for consistency with the docstring.

---

## Redis Key Summary

| Key pattern | Type | Content | TTL |
|---|---|---|---|
| `info:<code>:latest_quote` | String | Live tick: price, change, timestamp | None (overwritten every 15s) |
| `price:<code>:1m:<date>` | Hash | 1-min bars for one trading day | 2h after market close |
| `api:fund:<code>:history:<range>` | String (JSON) | Serialised daily history for chart API | 24h; deleted on DB write |
