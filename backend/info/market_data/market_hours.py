"""Per-exchange trading-hours helpers.

Maps the project's `listing_exchange` strings (e.g. "NYSE Arca", "SZ") to ISO MIC
codes and exposes `is_market_open`, `next_open`, `next_close`, `market_status`,
and `last_session` backed by `exchange_calendars`.

US extended hours (4:00–20:00 ET on regular session days) are padded in this
module since `exchange_calendars` exposes regular sessions only.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd

logger = logging.getLogger(__name__)


EXCHANGE_TO_MIC: dict[str, str] = {
    'NYSE': 'XNYS',
    'NYSE ARCA': 'XNYS',
    'NASDAQ': 'XNAS',
    'SH': 'XSHG',
    'SZ': 'XSHG',
}

US_MICS: frozenset[str] = frozenset({'XNYS', 'XNAS'})

# US extended-hours window in ET, padded around the regular 9:30–16:00 session.
US_EXTENDED_OPEN = time(4, 0)
US_EXTENDED_CLOSE = time(20, 0)
US_TZ = ZoneInfo('America/New_York')


def _resolve_mic(exchange: str) -> str | None:
    if not exchange:
        return None
    key = exchange.strip().upper()
    return EXCHANGE_TO_MIC.get(key)


@lru_cache(maxsize=8)
def _calendar(mic: str) -> xcals.ExchangeCalendar:
    return xcals.get_calendar(mic)


def _to_utc(at: datetime | None) -> pd.Timestamp:
    if at is None:
        ts = pd.Timestamp.now(tz='UTC')
    else:
        ts = pd.Timestamp(at)
        if ts.tz is None:
            ts = ts.tz_localize('UTC')
        else:
            ts = ts.tz_convert('UTC')
    return ts


def _is_us_extended_open(cal: xcals.ExchangeCalendar, ts: pd.Timestamp) -> bool:
    """True if `ts` falls within the 4:00–20:00 ET window on a US session day."""
    local = ts.tz_convert(US_TZ)
    session = local.normalize().tz_localize(None).date()
    try:
        if not cal.is_session(pd.Timestamp(session)):
            return False
    except Exception:
        return False
    t = local.time()
    return US_EXTENDED_OPEN <= t < US_EXTENDED_CLOSE


def is_market_open(
    exchange: str,
    at: datetime | None = None,
    *,
    include_extended: bool = False,
) -> bool:
    """Return True if the exchange is in a trading session at `at` (UTC now if None).

    For US MICs with `include_extended=True`, the 4:00–20:00 ET pre/post window
    on regular session days counts as open.
    """
    mic = _resolve_mic(exchange)
    if mic is None:
        return False
    cal = _calendar(mic)
    ts = _to_utc(at)
    if cal.is_open_on_minute(ts, ignore_breaks=False):
        return True
    if include_extended and mic in US_MICS:
        return _is_us_extended_open(cal, ts)
    return False


def next_open(exchange: str, at: datetime | None = None) -> datetime | None:
    mic = _resolve_mic(exchange)
    if mic is None:
        return None
    cal = _calendar(mic)
    ts = _to_utc(at)
    try:
        nxt = cal.next_open(ts)
    except Exception:
        return None
    return nxt.to_pydatetime()


def next_close(exchange: str, at: datetime | None = None) -> datetime | None:
    mic = _resolve_mic(exchange)
    if mic is None:
        return None
    cal = _calendar(mic)
    ts = _to_utc(at)
    try:
        nxt = cal.next_close(ts)
    except Exception:
        return None
    return nxt.to_pydatetime()


def last_session(exchange: str, at: datetime | None = None) -> date | None:
    """Most recent completed (or in-progress) trading session date for `exchange`.

    Returns the session date in the exchange's local calendar — useful for
    locating the right Redis intraday key when the market is closed.
    """
    mic = _resolve_mic(exchange)
    if mic is None:
        return None
    cal = _calendar(mic)
    ts = _to_utc(at)
    try:
        session = cal.minute_to_session(ts, direction='previous')
    except Exception:
        try:
            session = cal.date_to_session(ts.normalize(), direction='previous')
        except Exception:
            return None
    if session is None:
        return None
    return pd.Timestamp(session).date()


def previous_session(exchange: str, before: date) -> date | None:
    """Trading session strictly before `before`, per the exchange calendar."""
    mic = _resolve_mic(exchange)
    if mic is None:
        return None
    cal = _calendar(mic)
    try:
        prev = cal.previous_session(pd.Timestamp(before))
    except Exception:
        return None
    if prev is None:
        return None
    return pd.Timestamp(prev).date()


def recent_sessions(exchange: str, n: int, before: date | None = None) -> list[date]:
    """Return the most recent `n` trading sessions ending at `before` (inclusive
    if `before` is itself a session, otherwise the next-prior session)."""
    if n <= 0:
        return []
    last = last_session(exchange, datetime.combine(before, time(23, 59), tzinfo=timezone.utc)) if before else last_session(exchange)
    if last is None:
        return []
    sessions = [last]
    while len(sessions) < n:
        prev = previous_session(exchange, sessions[-1])
        if prev is None:
            break
        sessions.append(prev)
    return sessions


def market_status(exchange: str, at: datetime | None = None) -> dict:
    """Snapshot suitable for templates / JSON responses."""
    mic = _resolve_mic(exchange)
    if mic is None:
        return {'exchange': exchange, 'mic': None, 'is_open': False}
    ts = _to_utc(at)
    open_regular = is_market_open(exchange, at, include_extended=False)
    open_extended = (
        mic in US_MICS
        and not open_regular
        and is_market_open(exchange, at, include_extended=True)
    )
    if open_regular:
        session = 'regular'
    elif open_extended:
        session = 'extended'
    else:
        session = 'closed'
    return {
        'exchange': exchange,
        'mic': mic,
        'is_open': open_regular or open_extended,
        'session': session,
        'next_open': next_open(exchange, at),
        'next_close': next_close(exchange, at) if (open_regular or open_extended) else None,
        'last_session': last_session(exchange, at),
        'at': ts.to_pydatetime().replace(tzinfo=timezone.utc),
    }
