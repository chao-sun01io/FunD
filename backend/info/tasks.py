# This is to define tasks for the Celery worker.

from celery import shared_task
import pandas_market_calendars  as market_cal
from datetime import datetime, timedelta
import requests
import pandas as pd
from io import StringIO

from info.utils import redis_conn
from info.market_data import data_api

@shared_task
def example_add(x, y):
    """
    A simple task that adds two numbers.
    This is just a placeholder for demonstration purposes.
    """
    return x + y


def get_last_trading_day():
    """
    Returns the last trading day as a string in the format MM_DD_YYYY.
    using pandas-market-calendar.
    """
    nyse = market_cal.get_calendar('NYSE')
    today = datetime.now().date()
    schedule = nyse.schedule(start_date=today - timedelta(days=10), end_date=today)
    # Find the last trading day before today
    last_trading_days = schedule.index[schedule.index.date < today]
    last_trading_day = last_trading_days[-1]
    return last_trading_day.strftime("%m_%d_%Y")  # Format: MM_DD_YYYY


def get_holdings_kweb(date_str=None):
    """
    Retrieves the holdings from the KWEB website.
    """
    if date_str is None:
        raise ValueError("date_str must be provided in the format MM_DD_YYYY")

    # e.g. https://kraneshares.com/csv/07_16_2025_kweb_holdings.csv
    base_url = "https://kraneshares.com/csv/"
    pcf_path = date_str + "_kweb_holdings.csv"
    url = base_url + pcf_path
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": "https://www.google.com/",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    response = requests.get(url,headers=headers)
    if response.status_code == 200:
        df = pd.read_csv(StringIO(response.content.decode('utf-8')), header=1)
        # keep only the relevant columns [Company Name, Ticker, % of Net Assets, Identifier]
        df.rename(columns={'% of Net Assets': 'Weight','Ticker': 'Symbol'}, inplace=True)
        df = df[['Company Name', 'Symbol', 'Weight', 'Identifier']]
        df['Weight'] = df['Weight'].astype(float) / 100.0

        # Data cleaning
        # remove row with Cash or cash in Company Name
        # df = df[~df['Company Name'].str.contains('Cash', case =False, na=False)]
        # replace symbol 'YY' with 'JOYY'
        df['Symbol'] = df['Symbol'].replace('YY', 'JOYY')
        
        redis = redis_conn.get_redis_conn()
        redis.set(f"kweb_holdings_{date_str}", df.to_json(orient='records'))


@shared_task
def fetch_pcf_kweb(security_code=None):
    """
    It fetches the pcf for KWEB
    TODO: how to fetch pcf for any security by security_code
    """
    date_str = get_last_trading_day()
    holdings_df = get_holdings_kweb(date_str)
    return holdings_df

@shared_task
def fetch_kweb_price():
    '''
    '''
    price = data_api.get_quotes_from_sina_us(['KWEB'])
    redis = redis_conn.get_redis_conn()
    redis.set("info:kweb:latest_quote", str(price))