import json
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta

from django.conf import settings

from info.market_data.base import NAVPoint, OHLCVBar, ProviderError
from info.market_data.persistence import load_bars_from_db, persist_bars
from info.market_data.registry import (
    fetch_intraday_from_chain,
    fetch_nav_from_chain,
    fetch_ohlcv_from_chain,
)
from info.utils.redis_conn import get_redis_conn

logger = logging.getLogger(__name__)

CACHE_VERSION = 'v1'  # bump when response shape changes
FRESHNESS_TTL = 60 * 60  # 1 hour — gates back-gap provider fetches

RANGE_DAYS = {
    '1M': 30,
    '3M': 90,
    '6M': 180,
    'YTD': None,
    '1Y': 365,
    'all': None,
}


@dataclass
class IncompleteReport:
    """Summary of rows with NULL fields for a fund."""
    fund_code: str
    total_rows: int = 0
    incomplete_rows: int = 0
    field_nulls: dict[str, int] = field(default_factory=dict)
    ranges: list[tuple[date, date]] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        return self.incomplete_rows == 0


def _collapse_dates(dates: list[date], tolerance_days: int = 5) -> list[tuple[date, date]]:
    """Collapse a sorted list of dates into contiguous ranges with a gap tolerance."""
    if not dates:
        return []
    ranges = []
    start = dates[0]
    prev = dates[0]
    for d in dates[1:]:
        if (d - prev).days <= tolerance_days:
            prev = d
        else:
            ranges.append((start, prev))
            start = d
            prev = d
    ranges.append((start, prev))
    return ranges


def _range_start(range_key: str) -> date | None:
    """Return the start date for a range key, or None for 'all'."""
    if range_key == 'YTD':
        return date(date.today().year, 1, 1)
    days = RANGE_DAYS.get(range_key)
    if days is None:
        return None
    return date.today() - timedelta(days=days)


def _bar_to_dict(bar: OHLCVBar) -> dict:
    return {
        'time': str(bar.date),
        'open': float(bar.open) if bar.open is not None else None,
        'close': float(bar.close) if bar.close is not None else None,
        'high': float(bar.high) if bar.high is not None else None,
        'low': float(bar.low) if bar.low is not None else None,
        'volume': bar.volume,
        'nav': float(bar.nav) if bar.nav is not None else None,
    }


def _merge_nav(bars: list[OHLCVBar], nav_points: list[NAVPoint]) -> None:
    """In-place: attach NAV to OHLCV bars by date (for the legacy path)."""
    if not nav_points:
        return
    nav_by_date = {p.date: p.nav for p in nav_points}
    for bar in bars:
        nav = nav_by_date.get(bar.date)
        if nav is not None:
            bar.nav = nav


_ALL_FIELDS: tuple[str, ...] = ('open', 'high', 'low', 'close', 'volume', 'nav')


def _incomplete_dates(
    bars: list[OHLCVBar],
    fields: tuple[str, ...] | list[str] | None = None,
) -> list[date]:
    """Dates among loaded bars that have at least one NULL field.

    `fields`: subset of OHLCVBar fields to check. Defaults to all six.
    """
    check = fields if fields is not None else _ALL_FIELDS
    return [
        bar.date for bar in bars
        if any(getattr(bar, f) is None for f in check)
    ]


def _compute_gaps(
    bars: list[OHLCVBar],
    start: date,
    end: date,
    back_gap_allowed: bool,
) -> list[tuple[date, date]]:
    """Return the ranges to fetch from providers.

    Three sources, merged:
    - DB empty → one gap = (start, end)
    - Front gap [start, db_min-1] if db_min > start (always honored)
    - Back gap [db_max+1, end] if db_max < end (gated on back_gap_allowed)
    - Incomplete-row ranges: dates within [db_min, db_max] where any field is
      NULL, collapsed into contiguous ranges (gated on back_gap_allowed — same
      rationale as back gap: avoid hammering providers within the freshness
      window if they just couldn't supply the data)
    """
    if not bars:
        return [(start, end)]

    existing_dates = {bar.date for bar in bars}
    db_min = min(existing_dates)
    db_max = max(existing_dates)

    gaps: list[tuple[date, date]] = []

    if db_min > start:
        gaps.append((start, db_min - timedelta(days=1)))

    if back_gap_allowed:
        incomplete = _incomplete_dates(bars)
        if incomplete:
            gaps.extend(_collapse_dates(sorted(incomplete)))

        if db_max < end:
            gaps.append((db_max + timedelta(days=1), end))

    return gaps


def _freshness_key(symbol: str) -> str:
    return f'mktdata:{symbol}:last_check_at'


def _is_fresh(redis, symbol: str) -> bool:
    return bool(redis.exists(_freshness_key(symbol)))


def _mark_fresh(redis, symbol: str) -> None:
    redis.setex(_freshness_key(symbol), FRESHNESS_TTL, '1')


def _fetch_gap(symbol: str, gap_start: date, gap_end: date) -> tuple[list[OHLCVBar], list[NAVPoint]]:
    """Best-effort fetch of both OHLCV and NAV for a gap range."""
    try:
        bars = fetch_ohlcv_from_chain(symbol, gap_start, gap_end)
    except ProviderError as exc:
        logger.warning("OHLCV gap fetch failed for %s [%s, %s]: %s", symbol, gap_start, gap_end, exc)
        bars = []
    # Skip separate NAV fetch if OHLCV bars already carry NAV data
    if bars and all(b.nav is not None for b in bars):
        nav_points = []
    else:
        try:
            nav_points = fetch_nav_from_chain(symbol, gap_start, gap_end)
        except ProviderError as exc:
            logger.info("NAV gap fetch skipped for %s [%s, %s]: %s", symbol, gap_start, gap_end, exc)
            nav_points = []
    return bars, nav_points


def _provider_only_history(symbol: str, start: date, end: date) -> list[OHLCVBar]:
    """Legacy flow used when the fund is not registered in FundBasicInfo.
    Fetches OHLCV + NAV from providers, merges, returns — no DB writes."""
    try:
        bars = fetch_ohlcv_from_chain(symbol, start, end)
    except ProviderError:
        logger.exception("Failed to fetch historical data for %s", symbol)
        return []

    try:
        nav_points = fetch_nav_from_chain(symbol, start, end)
    except ProviderError as exc:
        logger.info("NAV fetch skipped for %s: %s", symbol, exc)
        nav_points = []

    _merge_nav(bars, nav_points)
    return bars


class HistoricalDataService:

    def get_history(self, fund_code: str, range_key: str = '1Y') -> list[dict]:
        """Redis cache → DB (if fresh) → full provider fetch + upsert."""
        start = _range_start(range_key)
        if start is None:
            start = date.today() - timedelta(days=365)
        end = date.today()
        symbol = fund_code.upper()

        redis = get_redis_conn()

        # Tier 1: Redis response cache
        cache_key = f'api:fund:{symbol}:history:{CACHE_VERSION}:{start}:{end}'
        cached = redis.get(cache_key)
        if cached:
            logger.debug("Cache hit for %s", cache_key)
            return json.loads(cached)

        # Look up fund; if absent, return None
        from info.models import FundBasicInfo
        fund = FundBasicInfo.objects.filter(fund_code=symbol).first()

        if fund is None:
            logger.debug("fund %s not in FundBasicInfo", symbol)
            return None

        # Tier 2: if fresh, serve from DB without hitting providers
        if _is_fresh(redis, symbol):
            bars = load_bars_from_db(fund, start, end)
            data = [_bar_to_dict(bar) for bar in bars]
            self._write_response_cache(redis, cache_key, data)
            return data

        # Tier 3: stale — fetch full range from providers, upsert to DB
        logger.debug("fetching full range %s [%s, %s]", symbol, start, end)
        fetched_bars, nav_points = _fetch_gap(symbol, start, end)
        try:
            persist_bars(fund, fetched_bars, nav_points)
        except Exception:
            logger.exception("persist_bars failed for %s", symbol)
        _mark_fresh(redis, symbol)

        # Read from DB (includes both old + newly upserted rows)
        bars = load_bars_from_db(fund, start, end)
        data = [_bar_to_dict(bar) for bar in bars]
        self._write_response_cache(redis, cache_key, data)
        return data

    def find_incomplete(
        self,
        fund_code: str,
        start: date | None = None,
        end: date | None = None,
        fields: list[str] | tuple[str, ...] | None = None,
    ) -> 'IncompleteReport':
        """Find DB rows with NULL fields and return date ranges that need re-fetching.

        Args:
            fund_code: Fund code to check.
            start: Start date (defaults to 1 year ago).
            end: End date (defaults to today).
            fields: Which fields to check for NULLs. Defaults to all OHLCV + nav.
                    Valid: 'open', 'high', 'low', 'close', 'volume', 'nav'.

        Returns:
            IncompleteReport with per-field breakdown and collapsed date ranges.

        One DB query (`load_bars_from_db`); all analysis is done in Python.
        """
        from info.models import FundBasicInfo

        symbol = fund_code.upper()
        fund = FundBasicInfo.objects.filter(fund_code=symbol).first()
        if fund is None:
            return IncompleteReport(fund_code=symbol)

        if start is None:
            start = date.today() - timedelta(days=365)
        if end is None:
            end = date.today()

        check_fields = tuple(fields) if fields else _ALL_FIELDS
        invalid = set(check_fields) - set(_ALL_FIELDS)
        if invalid:
            raise ValueError(f"Unknown fields: {invalid}. Valid: {_ALL_FIELDS}")

        bars = load_bars_from_db(fund, start, end)
        incomplete_dates = sorted(_incomplete_dates(bars, check_fields))

        field_nulls = {
            f: count for f in check_fields
            if (count := sum(1 for b in bars if getattr(b, f) is None))
        }

        return IncompleteReport(
            fund_code=symbol,
            total_rows=len(bars),
            incomplete_rows=len(incomplete_dates),
            field_nulls=field_nulls,
            ranges=_collapse_dates(incomplete_dates),
        )

    def get_intraday(self, fund_code: str) -> list[dict]:
        """Read 1-min bars from Redis.

        - Market open  → return today's bars; mark interest so the Celery poller
          keeps refreshing this symbol (lazy polling, 5-min TTL).
        - Market closed → return the most recent trading session's bars (looked
          up via `exchange_calendars`). No interest marker — nothing to poll.

        Returns list of dicts with unix timestamps suitable for LightweightCharts.
        """
        from info.market_data.market_hours import is_market_open, last_session
        from info.models import FundBasicInfo
        from info.tasks import mark_interest

        symbol = fund_code.upper()
        redis = get_redis_conn()

        fund = FundBasicInfo.objects.filter(fund_code=symbol).first()
        exchange = fund.listing_exchange if fund else None

        logger.debug("get_intraday for %s (exchange: %s)", symbol, exchange)

        if exchange and is_market_open(exchange, include_extended=True):
            mark_interest(redis, symbol)
            # Live: Redis-only — the poller is filling this hash every 15s.
            return self._read_intraday_bars(redis, symbol, date.today())

        # Closed: serve the last trading session. Redis first, provider fallback
        # (cached back to Redis) if missing.
        bar_date = last_session(exchange)
        if bar_date is None:
            return []

        return self._read_intraday_bars(redis, symbol, bar_date, allow_provider_fallback=True)

    @staticmethod
    def _read_intraday_bars(
        redis,
        symbol: str,
        bar_date: date,
        allow_provider_fallback: bool = False,
    ) -> list[dict]:
        """Parse Redis hash of 1-min bars into sorted list of dicts.

        If Redis has no bars for `bar_date` and `allow_provider_fallback=True`,
        fetch 1-min bars from the data provider (yfinance) and write them back
        to Redis using the same hash schema as `poll_live_quotes`.
        """
        key = f'price:{symbol}:1m:{bar_date.isoformat()}'
        raw_bars = redis.hgetall(key)
        if not raw_bars:
            if not allow_provider_fallback:
                return []
            bars = HistoricalDataService._fetch_intraday_from_provider(symbol, bar_date)
            if not bars:
                return []
            HistoricalDataService._cache_intraday_to_redis(redis, symbol, bar_date, bars)
            return bars

        from datetime import datetime, timezone
        bars = []
        for time_slot, bar_json in raw_bars.items():
            if isinstance(time_slot, bytes):
                time_slot = time_slot.decode()
            if isinstance(bar_json, bytes):
                bar_json = bar_json.decode()

            bar = json.loads(bar_json)
            # Build unix timestamp from date + HH:MM
            dt = datetime.strptime(
                f'{bar_date.isoformat()} {time_slot}',
                '%Y-%m-%d %H:%M',
            ).replace(tzinfo=timezone.utc)

            bars.append({
                'time': int(dt.timestamp()),
                'open': bar['o'],
                'high': bar['h'],
                'low': bar['l'],
                'close': bar['c'],
                'volume': bar.get('v'),
            })

        bars.sort(key=lambda b: b['time'])
        return bars

    @staticmethod
    def _write_response_cache(redis, cache_key: str, data: list[dict]) -> None:
        ttl = getattr(settings, 'HISTORY_CACHE_TTL', 86400)
        redis.setex(cache_key, ttl, json.dumps(data))

    @staticmethod
    def _fetch_intraday_from_provider(symbol: str, bar_date: date) -> list[dict]:
        """Fetch 1-min OHLCV bars for `bar_date` from the intraday provider chain.

        Returns chart-format dicts (`time` is unix-seconds UTC), sorted
        oldest→newest. Empty list on unsupported symbol, provider error, or no
        data (e.g. yfinance only retains 1-min data for the last ~30 days).
        """
        try:
            bars = fetch_intraday_from_chain(symbol, bar_date)
        except ProviderError as exc:
            logger.warning("intraday fetch failed for %s %s: %s", symbol, bar_date, exc)
            return []

        chart_bars = [
            {
                'time': int(bar.ts.timestamp()),
                'open': bar.open,
                'high': bar.high,
                'low': bar.low,
                'close': bar.close,
                'volume': bar.volume or 0,
            }
            for bar in bars
        ]
        chart_bars.sort(key=lambda b: b['time'])
        logger.info("intraday: %d bars for %s on %s", len(chart_bars), symbol, bar_date)
        return chart_bars

    @staticmethod
    def _cache_intraday_to_redis(redis, symbol: str, bar_date: date, bars: list[dict]) -> None:
        """Write chart-format bars into the same hash schema as `poll_live_quotes`.

        Hash key: `price:<symbol>:1m:<bar_date>`. Field: `HH:MM` UTC. Value:
        `{o,h,l,c,v}` JSON. 48h TTL matches the live poller.
        """
        if not bars:
            return
        from datetime import datetime, timezone
        key = f'price:{symbol}:1m:{bar_date.isoformat()}'
        mapping: dict[str, str] = {}
        for b in bars:
            slot = datetime.fromtimestamp(b['time'], tz=timezone.utc).strftime('%H:%M')
            mapping[slot] = json.dumps({
                'o': b['open'],
                'h': b['high'],
                'l': b['low'],
                'c': b['close'],
                'v': b.get('volume') or 0,
            })
        if mapping:
            redis.hset(key, mapping=mapping)
            redis.expire(key, 60 * 60 * 48)
