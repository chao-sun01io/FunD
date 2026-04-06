import logging
import re
from datetime import date
from decimal import Decimal

import akshare as ak

from info.market_data.base import HistoricalProvider, OHLCVBar, ProviderError

logger = logging.getLogger(__name__)

_CN_PATTERN = re.compile(r'^\d{6}\.(SZ|SH|BJ)$', re.IGNORECASE)

# Map exchange suffix to Sina prefix
_EXCHANGE_PREFIX = {
    'SZ': 'sz',
    'SH': 'sh',
    'BJ': 'bj',
}


class AkShareProvider(HistoricalProvider):
    """Historical OHLCV via akshare's fund_etf_hist_sina. Best for CN A-share funds/ETFs."""

    def supports_symbol(self, symbol: str) -> bool:
        return bool(_CN_PATTERN.match(symbol))

    def get_daily_ohlcv(
        self,
        symbol: str,
        start_date: date,
        end_date: date | None = None,
    ) -> list[OHLCVBar]:
        if end_date is None:
            end_date = date.today()

        # Convert "164906.SZ" -> "sz164906"
        code, exchange = symbol.split('.')
        prefix = _EXCHANGE_PREFIX.get(exchange.upper(), 'sz')
        sina_symbol = f'{prefix}{code}'

        try:
            df = ak.fund_etf_hist_sina(symbol=sina_symbol)
        except Exception as exc:
            raise ProviderError(f"akshare failed for {symbol}: {exc}") from exc

        if df is None or df.empty:
            logger.warning("akshare returned no data for %s", symbol)
            return []

        # Filter to requested date range
        df['date'] = df['date'].apply(lambda d: date.fromisoformat(str(d)) if not isinstance(d, date) else d)
        df = df[(df['date'] >= start_date) & (df['date'] <= end_date)]

        bars: list[OHLCVBar] = []
        for _, row in df.iterrows():
            def _dec(val):
                if val is None:
                    return None
                return Decimal(str(round(float(val), 4)))

            bars.append(OHLCVBar(
                date=row['date'] if isinstance(row['date'], date) else date.fromisoformat(str(row['date'])),
                open=_dec(row.get('open')),
                high=_dec(row.get('high')),
                low=_dec(row.get('low')),
                close=_dec(row.get('close')),
                volume=int(row['volume']) if row.get('volume') else None,
            ))
        return bars
