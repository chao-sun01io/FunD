import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


# Shared symbol pattern: CN exchange-listed fund, e.g. "164906.SZ", "510300.SH".
CN_SYMBOL_PATTERN = re.compile(r'^\d{6}\.(SZ|SH|BJ)$', re.IGNORECASE)


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
    nav: Decimal | None = None


@dataclass
class NAVPoint:
    """One day of official unit NAV for a fund."""
    date: date
    nav: Decimal


@dataclass
class IntradayBar:
    """One minute-scale OHLCV bar, timestamped (timezone-aware UTC).

    Prices are plain floats — intraday data is chart-only (served via Redis
    JSON to LightweightCharts), not persisted, so it does not need the Decimal
    precision that daily `OHLCVBar` does.
    """
    ts: datetime
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
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


class NAVProvider(ABC):
    """Fetches historical daily unit NAV from an external data source."""

    @abstractmethod
    def get_daily_nav(
        self,
        symbol: str,
        start_date: date,
        end_date: date | None = None,
    ) -> list[NAVPoint]:
        """Return daily NAV points for [start_date, end_date].
        end_date defaults to today if not supplied.
        Raises ProviderError on failure."""
        ...

    @abstractmethod
    def supports_symbol(self, symbol: str) -> bool:
        """Return True if this provider can service the given symbol."""
        ...


class IntradayProvider(ABC):
    """Fetches intraday (minute-scale) OHLCV bars from an external data source."""

    @abstractmethod
    def get_intraday_ohlcv(
        self,
        symbol: str,
        bar_date: date,
    ) -> list[IntradayBar]:
        """Return 1-minute OHLCV bars for `bar_date` (incl. pre/post market),
        sorted oldest→newest. Raises ProviderError on failure; may return []
        if the source has no intraday data for the symbol/date."""
        ...

    @abstractmethod
    def supports_symbol(self, symbol: str) -> bool:
        """Return True if this provider can service the given symbol."""
        ...
