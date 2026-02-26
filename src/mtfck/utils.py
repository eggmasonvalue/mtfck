from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
import logging
import requests

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def retry_request(
    stop_after=5,
    min_wait=1,
    max_wait=10,
    exceptions=(
        requests.exceptions.RequestException,
        ConnectionError,
        TimeoutError,
    ),
):
    """
    A standard retry decorator for network requests.

    Args:
        stop_after (int): Max number of attempts.
        min_wait (int): Minimum wait time between retries (seconds).
        max_wait (int): Maximum wait time between retries (seconds).
        exceptions (tuple): Tuple of exception types to retry on.
    """
    return retry(
        stop=stop_after_attempt(stop_after),
        wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
        retry=retry_if_exception_type(exceptions),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
