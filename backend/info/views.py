import json
import logging
from zoneinfo import ZoneInfo

from django.shortcuts import render, get_object_or_404

from .market_data.market_hours import market_status
from .models import FundBasicInfo, FundDailyData
from .utils.redis_conn import get_redis_conn

logger = logging.getLogger(__name__)


def index(request):
    funds = FundBasicInfo.objects.all()
    return render(request, 'info/index.html', {'funds': funds})


def detail(request, symbol):
    fund = get_object_or_404(FundBasicInfo, fund_code=symbol.upper())

    # Get latest tick from Redis (written by poll_live_quotes task)
    redis_client = get_redis_conn()
    tick_key = f"tick:{symbol.upper()}:latest"
    tick_raw = redis_client.get(tick_key)

    latest_price = None
    if tick_raw:
        try:
            if isinstance(tick_raw, bytes):
                tick_raw = tick_raw.decode('utf-8')
            tick = json.loads(tick_raw)
            latest_price = {
                'price': tick.get('price'),
                'change': tick.get('change'),
                'timestamp': tick.get('ts'),
            }
        except (json.JSONDecodeError, AttributeError) as e:
            logger.warning("Failed to parse tick for %s: %s", symbol, e)

    # Market status (open/closed, next open/close, last trading session)
    status = market_status(fund.listing_exchange)
    try:
        tz = ZoneInfo(fund.market_timezone)
    except Exception:
        tz = None
    if tz is not None:
        # Pre-format in the exchange's local tz — Django's |date filter would
        # otherwise re-convert tz-aware datetimes back to settings.TIME_ZONE.
        for key in ('next_open', 'next_close'):
            if status.get(key) is not None:
                local = status[key].astimezone(tz)
                status[f'{key}_display'] = local.strftime('%b %-d, %H:%M')

    # Last close from the most recent FundDailyData row
    last_daily = (
        FundDailyData.objects
        .filter(fund=fund, close__isnull=False)
        .order_by('-date')
        .first()
    )

    return render(request, 'info/detail.html', {
        'fund': fund,
        'latest_price': latest_price,
        'market_status': status,
        'last_daily': last_daily,
    })
