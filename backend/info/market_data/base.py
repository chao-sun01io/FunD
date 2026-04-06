from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


class ProviderError(Exception):
    """Raised when a market data provider fails (network, parse, rate limit)."""
    pass


@dataclass
class OHLCVBar:
    """One day of OHLCV data — the standard exchange format between
    providers, the service layer, and the database."""
    date: date
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    close: Decimal | None = None
    volume: int | None = None


class HistoricalProvider(ABC):
    """Fetches historical daily OHLCV from an external data source."""

    @abstractmethod
    def get_daily_ohlcv(
        self,
        symbol: str,
        start_date: date,
        end_date: date | None = None,
    ) -> list[OHLCVBar]:
        """Return daily OHLCV bars for [start_date, end_date].
        end_date defaults to today if not supplied.
        Raises ProviderError on failure."""
        ...

    @abstractmethod
    def supports_symbol(self, symbol: str) -> bool:
        """Return True if this provider can service the given symbol.
        Used by the fallback chain to skip irrelevant providers."""
        ...
