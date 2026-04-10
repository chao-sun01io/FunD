import logging
import re
import time
from datetime import date
from decimal import Decimal, InvalidOperation
from io import StringIO

import pandas as pd
import requests

from info.market_data.base import CN_SYMBOL_PATTERN, NAVPoint, NAVProvider, ProviderError

logger = logging.getLogger(__name__)

_API_URL = 'http://fund.eastmoney.com/f10/F10DataApi.aspx'
_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'
    ),
    'Referer': 'http://fundf10.eastmoney.com/',
}
_PER_PAGE = 40
_REQUEST_TIMEOUT = 10
_MAX_PAGES = 50  # safety cap; covers ~5.5 years at per=40

# Matches: content:"<table...>...</table>",records:123,pages:4,curpage:1
_APIDATA_RE = re.compile(
    r'content:"(?P<content>.*?)",records:(?P<records>\d+),pages:(?P<pages>\d+),curpage:(?P<curpage>\d+)',
    re.DOTALL,
)

_DATE_COL = '净值日期'
_NAV_COL = '单位净值'


class EastMoneyNAVProvider(NAVProvider):
    """Historical unit NAV via fund.eastmoney.com F10DataApi (lsjz endpoint).

    Supports CN exchange-listed funds (ETF / LOF) — symbol format NNNNNN.SZ|SH|BJ.
    EastMoney's API takes the bare 6-digit fund code.
    """

    def supports_symbol(self, symbol: str) -> bool:
        return bool(CN_SYMBOL_PATTERN.match(symbol))

    def get_daily_nav(
        self,
        symbol: str,
        start_date: date,
        end_date: date | None = None,
    ) -> list[NAVPoint]:
        if end_date is None:
            end_date = date.today()

        code = symbol.split('.')[0]
        sdate = start_date.isoformat()
        edate = end_date.isoformat()

        points: list[NAVPoint] = []
        page = 1
        total_pages = 1

        while page <= total_pages and page <= _MAX_PAGES:
            body = self._fetch_page(code, sdate, edate, page)
            content_html, total_pages = self._parse_envelope(body, symbol)
            if not content_html:
                break
            points.extend(self._parse_table(content_html, symbol))
            page += 1
            if page <= total_pages:
                time.sleep(0.2)  # be polite to eastmoney

        points.sort(key=lambda p: p.date)
        return points

    # ------- internals -------

    def _fetch_page(self, code: str, sdate: str, edate: str, page: int) -> str:
        params = {
            'type': 'lsjz',
            'code': code,
            'page': page,
            'sdate': sdate,
            'edate': edate,
            'per': _PER_PAGE,
        }
        try:
            resp = requests.get(
                _API_URL,
                params=params,
                headers=_HEADERS,
                timeout=_REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise ProviderError(f"eastmoney HTTP error for {code} page {page}: {exc}") from exc
        return resp.text

    def _parse_envelope(self, body: str, symbol: str) -> tuple[str, int]:
        """Extract the inner HTML table and total page count from the JSONP envelope."""
        match = _APIDATA_RE.search(body)
        if not match:
            logger.debug("eastmoney body for %s: %s", symbol, body[:500])
            raise ProviderError(f"eastmoney envelope parse failed for {symbol}")
        content = match.group('content')
        try:
            pages = int(match.group('pages'))
        except ValueError:
            pages = 1
        return content, max(pages, 1)

    def _parse_table(self, html: str, symbol: str) -> list[NAVPoint]:
        if not html.strip():
            return []
        try:
            dfs = pd.read_html(StringIO(html))
        except ValueError:
            # No tables found — e.g. fund has no NAV in the requested range.
            logger.debug("eastmoney empty table for %s", symbol)
            return []
        except Exception as exc:
            raise ProviderError(f"eastmoney table parse failed for {symbol}: {exc}") from exc

        if not dfs:
            return []

        df = dfs[0]
        if _DATE_COL not in df.columns or _NAV_COL not in df.columns:
            raise ProviderError(
                f"eastmoney unexpected columns for {symbol}: {list(df.columns)}"
            )

        points: list[NAVPoint] = []
        for _, row in df.iterrows():
            raw_date = row[_DATE_COL]
            raw_nav = row[_NAV_COL]
            if pd.isna(raw_date) or pd.isna(raw_nav):
                continue
            try:
                d = date.fromisoformat(str(raw_date).strip())
            except ValueError:
                logger.debug("eastmoney bad date %r for %s", raw_date, symbol)
                continue
            try:
                nav = Decimal(str(raw_nav).strip())
            except (InvalidOperation, ValueError):
                logger.debug("eastmoney bad nav %r for %s on %s", raw_nav, symbol, d)
                continue
            points.append(NAVPoint(date=d, nav=nav))
        return points
