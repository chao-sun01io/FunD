import logging
from datetime import date, timedelta
from decimal import Decimal

import yfinance as yf

from info.market_data.base import HistoricalProvider, OHLCVBar, ProviderError

logger = logging.getLogger(__name__)

# CN A-share suffixes that yfinance does not support well
_CN_SUFFIXES = ('.SZ', '.SH', '.BJ')


class YFinanceProvider(HistoricalProvider):
    """Historical OHLCV via Yahoo Finance. Best for US-listed ETFs/stocks."""

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
            ))
        return bars
