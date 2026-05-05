import json
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta

from django.conf import settings

from info.market_data.base import NAVPoint, OHLCVBar, ProviderError
from info.market_data.persistence import load_bars_from_db, persist_bars
from info.market_data.registry import fetch_nav_from_chain, fetch_ohlcv_from_chain
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

    @staticmethod
    def _write_response_cache(redis, cache_key: str, data: list[dict]) -> None:
        ttl = getattr(settings, 'HISTORY_CACHE_TTL', 86400)
        redis.setex(cache_key, ttl, json.dumps(data))
