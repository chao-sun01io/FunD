import json
import logging
from datetime import datetime, timezone

from celery import shared_task
from django.conf import settings

from info.market_data.data_api import get_quotes_from_sina_us
from info.market_data.market_hours import is_market_open
from info.utils.redis_conn import get_redis_conn

logger = logging.getLogger(__name__)

_BAR_TTL = 60 * 60 * 48  # 2 days
INTEREST_TTL = 60 * 5  # 5 min — refreshed by each /fund_intraday request


def interest_key(symbol: str) -> str:
    return f'intraday:interest:{symbol.upper()}'


def mark_interest(redis, symbol: str) -> None:
    redis.setex(interest_key(symbol), INTEREST_TTL, '1')


def _active_symbols(redis, symbols: list[str]) -> list[str]:
    """Filter to symbols with (a) recent request interest and (b) open market."""
    from info.models import FundBasicInfo

    if not symbols:
        return []

    interested = [s for s in symbols if redis.exists(interest_key(s))]
    if not interested:
        return []

    funds = {
        f.fund_code: f for f in
        FundBasicInfo.objects.filter(fund_code__in=interested)
    }

    active: list[str] = []
    for symbol in interested:
        fund = funds.get(symbol)
        if fund is None:
            logger.debug("poll skip %s: not in FundBasicInfo", symbol)
            continue
        if not is_market_open(fund.listing_exchange, include_extended=True):
            logger.debug("poll skip %s: market closed (%s)", symbol, fund.listing_exchange)
            continue
        active.append(symbol)
    return active


@shared_task
def poll_live_quotes():
    """Poll Sina for tracked symbols, buffer ticks, and aggregate 1-min bars in Redis.

    Lazy: only polls symbols that have been requested via /fund_intraday in the
    last `INTEREST_TTL` seconds AND whose exchange is currently open.
    """
    symbols = getattr(settings, 'INTRADAY_SYMBOLS', ['KWEB'])
    redis = get_redis_conn()

    active = _active_symbols(redis, symbols)
    if not active:
        return
    
    logger.debug("poll_live_quotes: polling %d active symbols: %s", len(active), active)

    quotes = get_quotes_from_sina_us(active)
    if not quotes:
        return

    now = datetime.now(timezone.utc)
    today_str = now.strftime('%Y-%m-%d')
    minute_slot = now.strftime('%H:%M')

    for symbol, quote in quotes.items():
        # Store latest tick buffer
        tick_key = f'tick:{symbol}:latest'
        redis.setex(tick_key, 86400, json.dumps({
            'price': quote.price,
            'volume': quote.volume,
            'open': quote.open,
            'high': quote.high,
            'low': quote.low,
            'ts': now.isoformat(),
        }))

        # Aggregate into 1-min bar
        bar_hash_key = f'price:{symbol}:1m:{today_str}'
        existing_raw = redis.hget(bar_hash_key, minute_slot)

        if existing_raw:
            bar = json.loads(existing_raw)
            bar['h'] = max(bar['h'], quote.price)
            bar['l'] = min(bar['l'], quote.price)
            bar['c'] = quote.price
            bar['v'] = quote.volume
        else:
            bar = {
                'o': quote.price,
                'h': quote.price,
                'l': quote.price,
                'c': quote.price,
                'v': quote.volume,
            }

        redis.hset(bar_hash_key, minute_slot, json.dumps(bar))
        redis.expire(bar_hash_key, _BAR_TTL)

    logger.debug("poll_live_quotes: updated %d symbols at %s", len(quotes), minute_slot)
