from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
import requests

from info.market_data.base import ProviderError
from info.market_data.providers.eastmoney_nav_provider import EastMoneyNAVProvider


# Canned single-page response mimicking eastmoney F10DataApi `lsjz` payload.
# Real responses wrap an HTML table in a JSONP envelope.
SINGLE_PAGE_BODY = (
    'var apidata={ content:"'
    "<table class='w782 comm lsjz'>"
    "<thead><tr>"
    "<th>净值日期</th><th>单位净值</th><th>累计净值</th><th>日增长率</th>"
    "<th>申购状态</th><th>赎回状态</th><th>分红送配</th>"
    "</tr></thead>"
    "<tbody>"
    "<tr><td>2024-01-03</td><td>1.2345</td><td>1.5000</td><td>0.50%</td><td>开放</td><td>开放</td><td></td></tr>"
    "<tr><td>2024-01-02</td><td>1.2285</td><td>1.4940</td><td>-0.20%</td><td>开放</td><td>开放</td><td></td></tr>"
    '</tbody></table>",records:2,pages:1,curpage:1};'
)


def _mock_response(text: str, status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.text = text
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    return resp


class TestSupportsSymbol:
    @pytest.mark.parametrize("symbol", ["164906.SZ", "510300.SH", "159915.SZ", "110022.SH", "833100.BJ"])
    def test_accepts_cn_etf_lof(self, symbol):
        assert EastMoneyNAVProvider().supports_symbol(symbol) is True

    @pytest.mark.parametrize("symbol", ["SPY", "KWEB", "164906", "AAPL.US", "12345.SZ", "abcdef.SZ"])
    def test_rejects_non_cn(self, symbol):
        assert EastMoneyNAVProvider().supports_symbol(symbol) is False

    def test_case_insensitive_suffix(self):
        assert EastMoneyNAVProvider().supports_symbol("164906.sz") is True


class TestGetDailyNav:
    @patch('info.market_data.providers.eastmoney_nav_provider.time.sleep')
    @patch('info.market_data.providers.eastmoney_nav_provider.requests.get')
    def test_parses_single_page(self, mock_get, _mock_sleep):
        mock_get.return_value = _mock_response(SINGLE_PAGE_BODY)

        provider = EastMoneyNAVProvider()
        points = provider.get_daily_nav(
            '164906.SZ',
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        assert len(points) == 2
        # Should be sorted ascending by date
        assert points[0].date == date(2024, 1, 2)
        assert points[0].nav == Decimal('1.2285')
        assert points[1].date == date(2024, 1, 3)
        assert points[1].nav == Decimal('1.2345')

        # Verify request parameters
        call_kwargs = mock_get.call_args.kwargs
        assert call_kwargs['params']['code'] == '164906'
        assert call_kwargs['params']['type'] == 'lsjz'
        assert call_kwargs['params']['sdate'] == '2024-01-01'
        assert call_kwargs['params']['edate'] == '2024-01-31'
        assert 'User-Agent' in call_kwargs['headers']

    @patch('info.market_data.providers.eastmoney_nav_provider.time.sleep')
    @patch('info.market_data.providers.eastmoney_nav_provider.requests.get')
    def test_handles_multi_page(self, mock_get, _mock_sleep):
        page1 = (
            'var apidata={ content:"'
            "<table class='w782 comm lsjz'>"
            "<thead><tr><th>净值日期</th><th>单位净值</th><th>累计净值</th>"
            "<th>日增长率</th><th>申购状态</th><th>赎回状态</th><th>分红送配</th></tr></thead>"
            "<tbody>"
            "<tr><td>2024-02-02</td><td>1.3000</td><td>1.6000</td><td>0.10%</td><td>开放</td><td>开放</td><td></td></tr>"
            '</tbody></table>",records:2,pages:2,curpage:1};'
        )
        page2 = (
            'var apidata={ content:"'
            "<table class='w782 comm lsjz'>"
            "<thead><tr><th>净值日期</th><th>单位净值</th><th>累计净值</th>"
            "<th>日增长率</th><th>申购状态</th><th>赎回状态</th><th>分红送配</th></tr></thead>"
            "<tbody>"
            "<tr><td>2024-02-01</td><td>1.2990</td><td>1.5990</td><td>-0.10%</td><td>开放</td><td>开放</td><td></td></tr>"
            '</tbody></table>",records:2,pages:2,curpage:2};'
        )
        mock_get.side_effect = [_mock_response(page1), _mock_response(page2)]

        provider = EastMoneyNAVProvider()
        points = provider.get_daily_nav(
            '510300.SH',
            start_date=date(2024, 2, 1),
            end_date=date(2024, 2, 28),
        )

        assert mock_get.call_count == 2
        assert [p.date for p in points] == [date(2024, 2, 1), date(2024, 2, 2)]
        assert points[0].nav == Decimal('1.2990')
        assert points[1].nav == Decimal('1.3000')

    @patch('info.market_data.providers.eastmoney_nav_provider.requests.get')
    def test_http_error_raises_provider_error(self, mock_get):
        mock_get.side_effect = requests.ConnectionError("boom")

        with pytest.raises(ProviderError, match="eastmoney HTTP error"):
            EastMoneyNAVProvider().get_daily_nav(
                '164906.SZ',
                start_date=date(2024, 1, 1),
            )

    @patch('info.market_data.providers.eastmoney_nav_provider.requests.get')
    def test_malformed_envelope_raises_provider_error(self, mock_get):
        mock_get.return_value = _mock_response("<html>login required</html>")

        with pytest.raises(ProviderError, match="envelope parse failed"):
            EastMoneyNAVProvider().get_daily_nav(
                '164906.SZ',
                start_date=date(2024, 1, 1),
            )

    @patch('info.market_data.providers.eastmoney_nav_provider.requests.get')
    def test_empty_content_returns_empty_list(self, mock_get):
        body = 'var apidata={ content:"",records:0,pages:0,curpage:1};'
        mock_get.return_value = _mock_response(body)

        points = EastMoneyNAVProvider().get_daily_nav(
            '164906.SZ',
            start_date=date(2024, 1, 1),
        )
        assert points == []
