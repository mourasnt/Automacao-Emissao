import pytest
import time
from utils.retry import retry

counter = {"calls": 0}

@retry((RuntimeError,), tries=3, delay=0.1, backoff=1)
def flaky():
    counter["calls"] += 1
    if counter["calls"] < 3:
        raise RuntimeError("fail")
    return "ok"


def test_retry_eventually_succeeds():
    # Reset counter
    counter["calls"] = 0
    assert flaky() == "ok"
    assert counter["calls"] == 3
