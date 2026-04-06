import json
import logging
from datetime import date, timedelta

from django.conf import settings

from info.market_data.base import OHLCVBar, ProviderError
from info.market_data.registry import fetch_from_chain
from info.utils.redis_conn import get_redis_conn

logger = logging.getLogger(__name__)

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
    }


class HistoricalDataService:

    def get_history(self, fund_code: str, range_key: str = '1Y') -> list[dict]:
        """Redis cache -> external API. Returns chart-ready list of dicts."""
        start = _range_start(range_key)
        if start is None:
            start = date.today() - timedelta(days=365)
        end = date.today()
        symbol = fund_code.upper()

        # 1. Check Redis cache
        cache_key = f'api:fund:{symbol}:history:{start}:{end}'
        redis = get_redis_conn()
        cached = redis.get(cache_key)
        if cached:
            logger.debug("Cache hit for %s", cache_key)
            return json.loads(cached)

        # 2. Fetch from provider chain
        try:
            bars = fetch_from_chain(symbol, start, end)
        except ProviderError:
            logger.exception("Failed to fetch historical data for %s", fund_code)
            return []

        data = [_bar_to_dict(bar) for bar in bars]

        # 3. Cache the result
        ttl = getattr(settings, 'HISTORY_CACHE_TTL', 86400) # default to 24h
        redis.setex(cache_key, ttl, json.dumps(data))
        return data
