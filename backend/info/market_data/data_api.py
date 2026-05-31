import logging
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    "Referer": "https://finance.sina.com.cn/",
}


@dataclass
class SinaQuote:
    """Structured quote from Sina Finance."""
    symbol: str
    name: str
    price: float
    change: float
    open: float
    high: float
    low: float
    volume: int
    datetime: str


def get_quotes_from_sina_us(symbols: list[str]) -> dict[str, SinaQuote]:
    """Fetch latest quotes for US-listed symbols from Sina Finance.

    Returns a dict keyed by symbol (uppercase) with structured SinaQuote values.
    Sina field mapping: 0=name, 1=price, 2=change, 3=datetime, 5=open, 6=high, 7=low, 10=volume.
    """
    if not symbols:
        return {}

    url = "https://hq.sinajs.cn/list=" + ",".join(f"gb_{s.lower()}" for s in symbols)
    try:
        response = requests.get(url, headers=_HEADERS, timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Sina quote fetch failed: %s", exc)
        return {}

    quotes: dict[str, SinaQuote] = {}
    lines = response.text.split(';')
    for i, line in enumerate(lines):
        if not line or ',' not in line:
            continue
        parts = line.split(',')
        if len(parts) < 11:
            continue
        try:
            symbol = symbols[i].upper()
            quotes[symbol] = SinaQuote(
                symbol=symbol,
                name=parts[0].split('=')[1].strip('"'),
                price=float(parts[1]),
                change=float(parts[2]),
                datetime=parts[3].strip(),
                open=float(parts[5]),
                high=float(parts[6]),
                low=float(parts[7]),
                volume=int(parts[10]),
            )
        except (ValueError, IndexError) as exc:
            logger.warning("Failed to parse Sina quote for index %d: %s", i, exc)
            continue

    return quotes
