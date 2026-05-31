import datetime as dt
from unittest.mock import patch

import pandas as pd
import pytest

from info.market_data.base import IntradayBar, ProviderError
from info.market_data.providers.yfinance_provider import YFinanceProvider


@pytest.fixture
def provider():
    return YFinanceProvider()


def test_supports_symbol(provider):
    assert provider.supports_symbol('KWEB') is True
    assert provider.supports_symbol('510300.SH') is False
    assert provider.supports_symbol('164906.sz') is False


@patch('info.market_data.providers.yfinance_provider.yf.Ticker')
def test_get_intraday_ohlcv_success(mock_ticker, provider):
    idx = pd.to_datetime(
        ['2024-01-02 09:31:00', '2024-01-02 09:30:00']  # out of order on purpose
    ).tz_localize('America/New_York')
    df = pd.DataFrame({
        'Open': [101.0, 100.0],
        'High': [103.0, 102.0],
        'Low': [100.0, 99.0],
        'Close': [102.5, 101.5],
        'Volume': [6000, 5000],
    }, index=idx)
    mock_ticker.return_value.history.return_value = df

    bars = provider.get_intraday_ohlcv('KWEB', dt.date(2024, 1, 2))

    assert len(bars) == 2
    assert all(isinstance(b, IntradayBar) for b in bars)
    # Sorted oldest->newest regardless of input order.
    assert bars[0].ts < bars[1].ts
    assert bars[0].open == 100.0
    assert bars[0].close == 101.5
    assert bars[0].volume == 5000
    # Timestamps normalized to UTC (09:30 ET = 14:30 UTC).
    assert bars[0].ts.utcoffset() == dt.timedelta(0)
    assert (bars[0].ts.hour, bars[0].ts.minute) == (14, 30)
    # 1-minute interval requested, including pre/post market.
    _, kwargs = mock_ticker.return_value.history.call_args
    assert kwargs['interval'] == '1m'
    assert kwargs['prepost'] is True


@patch('info.market_data.providers.yfinance_provider.yf.Ticker')
def test_get_intraday_ohlcv_skips_nan_rows(mock_ticker, provider):
    idx = pd.to_datetime(
        ['2024-01-02 09:30:00', '2024-01-02 09:31:00']
    ).tz_localize('America/New_York')
    df = pd.DataFrame({
        'Open': [100.0, float('nan')],
        'High': [102.0, 103.0],
        'Low': [99.0, 100.0],
        'Close': [101.5, float('nan')],
        'Volume': [5000, float('nan')],
    }, index=idx)
    mock_ticker.return_value.history.return_value = df

    bars = provider.get_intraday_ohlcv('KWEB', dt.date(2024, 1, 2))

    assert len(bars) == 1
    assert bars[0].open == 100.0


@patch('info.market_data.providers.yfinance_provider.yf.Ticker')
def test_get_intraday_ohlcv_empty(mock_ticker, provider):
    mock_ticker.return_value.history.return_value = pd.DataFrame()
    assert provider.get_intraday_ohlcv('KWEB', dt.date(2024, 1, 2)) == []


@patch('info.market_data.providers.yfinance_provider.yf.Ticker')
def test_get_intraday_ohlcv_raises_provider_error(mock_ticker, provider):
    mock_ticker.return_value.history.side_effect = RuntimeError('boom')
    with pytest.raises(ProviderError):
        provider.get_intraday_ohlcv('KWEB', dt.date(2024, 1, 2))
