import json
import logging
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


def _compute_gaps(
    existing_dates: set[date],
    start: date,
    end: date,
    back_gap_allowed: bool,
) -> list[tuple[date, date]]:
    """Return the ranges to fetch from providers.

    - DB empty → one gap = (start, end)
    - Otherwise: front gap [start, db_min-1] if db_min > start (always)
                 back gap [db_max+1, end] if db_max < end AND back_gap_allowed
    """
    if not existing_dates:
        return [(start, end)]

    gaps: list[tuple[date, date]] = []
    db_min = min(existing_dates)
    db_max = max(existing_dates)

    if db_min > start:
        gaps.append((start, db_min - timedelta(days=1)))

    if back_gap_allowed and db_max < end:
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
        """3-tier cache: Redis response cache → DB → provider gap-fill."""
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

        # Look up fund; if absent, fall back to provider-only path
        # Local import to avoid touching Django ORM in non-DB contexts (tests).
        from info.models import FundBasicInfo
        fund = FundBasicInfo.objects.filter(fund_code=symbol).first()

        if fund is None:
            logger.debug("fund %s not in FundBasicInfo — provider-only path", symbol)
            
            # bars = _provider_only_history(symbol, start, end)
            # data = [_bar_to_dict(bar) for bar in bars]
            # self._write_response_cache(redis, cache_key, data)
            # return data
            
            return None

        # Tier 2: DB read
        bars = load_bars_from_db(fund, start, end)
        existing_dates = {bar.date for bar in bars}

        # Tier 3: gap computation & fill
        back_gap_allowed = not _is_fresh(redis, symbol)
        gaps = _compute_gaps(existing_dates, start, end, back_gap_allowed)

        if gaps:
            for gap_start, gap_end in gaps:
                logger.debug("gap fill %s [%s, %s]", symbol, gap_start, gap_end)
                gap_bars, gap_nav = _fetch_gap(symbol, gap_start, gap_end)
                try:
                    persist_bars(fund, gap_bars, gap_nav)
                except Exception:
                    logger.exception("persist_bars failed for %s", symbol)
            _mark_fresh(redis, symbol)
            # Re-read DB to get the newly persisted rows merged with existing
            bars = load_bars_from_db(fund, start, end)

        data = [_bar_to_dict(bar) for bar in bars]
        self._write_response_cache(redis, cache_key, data)
        return data

    @staticmethod
    def _write_response_cache(redis, cache_key: str, data: list[dict]) -> None:
        ttl = getattr(settings, 'HISTORY_CACHE_TTL', 86400)
        redis.setex(cache_key, ttl, json.dumps(data))
