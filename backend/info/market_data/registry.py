import importlib
import logging
from functools import lru_cache

from django.conf import settings

from info.market_data.base import HistoricalProvider, NAVProvider, ProviderError

logger = logging.getLogger(__name__)


def _import_class(dotted_path: str):
    module_path, class_name = dotted_path.rsplit('.', 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


@lru_cache(maxsize=None)
def get_historical_chain() -> list[HistoricalProvider]:
    """Load and instantiate the ordered list of historical providers from settings."""
    paths = getattr(settings, 'HISTORICAL_PROVIDERS', [])
    chain: list[HistoricalProvider] = []
    for path in paths:
        try:
            cls = _import_class(path)
            chain.append(cls())
        except Exception:
            logger.exception("Failed to load historical provider: %s", path)
    if not chain:
        logger.warning("No historical providers configured")
    return chain


@lru_cache(maxsize=None)
def get_nav_chain() -> list[NAVProvider]:
    """Load and instantiate the ordered list of NAV providers from settings."""
    paths = getattr(settings, 'NAV_PROVIDERS', [])
    chain: list[NAVProvider] = []
    for path in paths:
        try:
            cls = _import_class(path)
            chain.append(cls())
        except Exception:
            logger.exception("Failed to load NAV provider: %s", path)
    if not chain:
        logger.debug("No NAV providers configured")
    return chain


def fetch_ohlcv_from_chain(symbol, start_date, end_date=None):
    """Try each provider in the chain until one succeeds.
    Raises ProviderError if all fail."""
    chain = get_historical_chain()
    last_error = None
    for provider in chain:
        if not provider.supports_symbol(symbol):
            continue
        try:
            return provider.get_daily_ohlcv(symbol, start_date, end_date)
        except ProviderError as exc:
            logger.warning("Provider %s failed for %s: %s", type(provider).__name__, symbol, exc)
            last_error = exc
    raise ProviderError(f"All providers exhausted for {symbol}") from last_error


def fetch_nav_from_chain(symbol, start_date, end_date=None):
    """Try each NAV provider in the chain until one succeeds.
    Raises ProviderError if all fail or none support the symbol."""
    chain = get_nav_chain()
    last_error = None
    for provider in chain:
        if not provider.supports_symbol(symbol):
            continue
        try:
            return provider.get_daily_nav(symbol, start_date, end_date)
        except ProviderError as exc:
            logger.warning("NAV provider %s failed for %s: %s", type(provider).__name__, symbol, exc)
            last_error = exc
    raise ProviderError(f"All NAV providers exhausted for {symbol}") from last_error
