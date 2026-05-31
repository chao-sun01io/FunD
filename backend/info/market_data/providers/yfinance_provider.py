import logging
from datetime import date, timedelta
from decimal import Decimal

import yfinance as yf

from info.market_data.base import (
    HistoricalProvider,
    IntradayBar,
    IntradayProvider,
    OHLCVBar,
    ProviderError,
)

logger = logging.getLogger(__name__)

# CN A-share suffixes that yfinance does not support well
_CN_SUFFIXES = ('.SZ', '.SH', '.BJ')


class YFinanceProvider(HistoricalProvider, IntradayProvider):
    """Historical (daily + minute-scale) OHLCV via Yahoo Finance.
    Best for US-listed ETFs/stocks."""

    def supports_symbol(self, symbol: str) -> bool:
        return not symbol.upper().endswith(_CN_SUFFIXES)

    def get_daily_ohlcv(
        self,
        symbol: str,
        start_date: date,
        end_date: date | None = None,
    ) -> list[OHLCVBar]:
        if end_date is None:
            end_date = date.today()
        try:
            ticker = yf.Ticker(symbol)
            # yfinance end date is exclusive, so add one day
            df = ticker.history(
                start=start_date.isoformat(),
                end=(end_date + timedelta(days=1)).isoformat(),
                auto_adjust=True,
            )
        except Exception as exc:
            raise ProviderError(f"yfinance failed for {symbol}: {exc}") from exc

        if df.empty:
            logger.warning("yfinance returned no data for %s", symbol)
            return []

        bars: list[OHLCVBar] = []
        for ts, row in df.iterrows():
            bars.append(OHLCVBar(
                date=ts.date(),
                open=Decimal(str(round(row['Open'], 4))) if row.get('Open') is not None else None,
                high=Decimal(str(round(row['High'], 4))) if row.get('High') is not None else None,
                low=Decimal(str(round(row['Low'], 4))) if row.get('Low') is not None else None,
                close=Decimal(str(round(row['Close'], 4))) if row.get('Close') is not None else None,
                volume=int(row['Volume']) if row.get('Volume') is not None else None,
                nav=Decimal(str(round(row['Close'], 4))) if row.get('Close') is not None else None,
            ))
        return bars

    def get_intraday_ohlcv(
        self,
        symbol: str,
        bar_date: date,
    ) -> list[IntradayBar]:
        """1-minute OHLCV bars for `bar_date`, including pre/post-market.

        Yahoo only retains 1-minute data for roughly the last 30 days, so older
        dates return []. Timestamps are normalized to timezone-aware UTC.
        """
        try:
            df = yf.Ticker(symbol).history(
                start=bar_date.isoformat(),
                end=(bar_date + timedelta(days=1)).isoformat(),
                interval='1m',
                prepost=True,
                auto_adjust=False,
            )
        except Exception as exc:
            raise ProviderError(
                f"yfinance 1m failed for {symbol} on {bar_date}: {exc}"
            ) from exc

        if df is None or df.empty:
            logger.warning("yfinance returned no 1m data for %s on %s", symbol, bar_date)
            return []

        bars: list[IntradayBar] = []
        for ts, row in df.iterrows():
            ts_utc = ts.tz_convert('UTC') if ts.tz is not None else ts.tz_localize('UTC')
            o, c = row.get('Open'), row.get('Close')
            # Skip rows with no usable open/close (NaN or missing).
            if o is None or c is None or o != o or c != c:
                continue
            h, l, v = row.get('High'), row.get('Low'), row.get('Volume')
            bars.append(IntradayBar(
                ts=ts_utc.to_pydatetime(),
                open=float(o),
                high=float(h) if h is not None and h == h else float(o),
                low=float(l) if l is not None and l == l else float(o),
                close=float(c),
                volume=int(v) if v is not None and v == v else 0,  # NaN guard
            ))
        bars.sort(key=lambda b: b.ts)
        return bars
