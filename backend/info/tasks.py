# This is to define tasks for the Celery worker.

from celery import shared_task

from info.utils import redis_conn
from info.market_data import data_api


@shared_task
def fetch_kweb_price():
    '''
    '''
    price = data_api.get_quotes_from_sina_us(['KWEB'])
    redis = redis_conn.get_redis_conn()
    redis.set("info:kweb:latest_quote", str(price))