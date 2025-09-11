import redis
from django.conf import settings
from functools import lru_cache

@lru_cache(maxsize=None)
def get_redis_pool():
    """
    Creates and caches a single Redis connection pool.
    This function will only run its code the first time it's called.
    
    Because of setting is a LazySettings object, we need to
    access it at runtime, not at import time.
    """
    info_store_settings = settings.REDIS_CONNECTIONS['INFO_STORE']
    return redis.ConnectionPool(
        host=info_store_settings['host'],
        port=info_store_settings['port'],
        db=info_store_settings['db'],
        max_connections=info_store_settings['connection_pool']['max_connections'],
        socket_timeout=info_store_settings['connection_pool']['timeout']
    )

def get_redis_conn():
    """
    Returns a Redis connection from the shared pool.
    This is safe to call from anywhere in your app.
    """
    pool = get_redis_pool()
    return redis.Redis(connection_pool=pool)