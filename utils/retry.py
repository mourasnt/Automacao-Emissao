import time
import functools
from typing import Callable, Type, Tuple


def retry(on_exception: Tuple[Type[Exception], ...] = (Exception,), tries: int = 3, delay: float = 1.0, backoff: float = 2.0, logger=None):
    """Retry decorator with exponential backoff.

    Example:
        @retry((gspread.exceptions.APIError,), tries=5, delay=2)
        def call_api(...):
            ...
    """
    def deco(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            mtries, mdelay = tries, delay
            last_exc = None
            while mtries > 0:
                try:
                    return func(*args, **kwargs)
                except on_exception as e:
                    last_exc = e
                    if logger:
                        logger.warning(f"Retryable exception: {e}. Retrying in {mdelay}s (tries left: {mtries-1})")
                    time.sleep(mdelay)
                    mtries -= 1
                    mdelay *= backoff
            # If we get here, all retries failed
            if logger:
                logger.error(f"All retries failed for function {func.__name__}: {last_exc}")
            raise last_exc
        return wrapper
    return deco
