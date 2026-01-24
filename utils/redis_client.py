import redis
from loguru import logger
from utils.retry import retry


@retry((redis.exceptions.ConnectionError,), tries=5, delay=1, backoff=2, logger=logger)
def get_redis(host: str, port: int, db: int = 0, decode_responses: bool = True) -> redis.Redis:
    """Return a connected Redis client (pings to verify connection)."""
    r = redis.Redis(host=host, port=port, db=db, decode_responses=decode_responses)
    r.ping()
    logger.success(f"Conectado ao Redis em {host}:{port} (db={db})")
    return r
