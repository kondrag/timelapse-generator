"""Retry utilities for network operations."""

import time
import functools
import logging
from typing import Callable, Type, Union, Tuple, Any

logger = logging.getLogger(__name__)


def retry(
    exceptions: Union[Type[Exception], Tuple[Type[Exception], ...]],
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    jitter: float = 0.1
):
    """Retry decorator for functions that may fail.

    Args:
        exceptions: Exception or tuple of exceptions to catch
        max_attempts: Maximum number of retry attempts
        delay: Initial delay between retries in seconds
        backoff: Multiplier for delay after each attempt
        jitter: Random jitter to add to delay (0-1, fraction of delay)

    Returns:
        Decorator function
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            attempt = 0
            current_delay = delay

            while attempt < max_attempts:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    attempt += 1
                    if attempt >= max_attempts:
                        logger.error(f"Function {func.__name__} failed after {max_attempts} attempts: {e}")
                        raise

                    # Add jitter to delay
                    import random
                    jitter_amount = current_delay * jitter * random.random()
                    actual_delay = current_delay + jitter_amount

                    logger.warning(
                        f"Function {func.__name__} failed (attempt {attempt}/{max_attempts}): {e}. "
                        f"Retrying in {actual_delay:.2f} seconds..."
                    )
                    time.sleep(actual_delay)
                    current_delay *= backoff

            return None  # Should never reach here

        return wrapper
    return decorator


def exponential_backoff(attempt: int, base_delay: float = 1.0, max_delay: float = 60.0) -> float:
    """Calculate exponential backoff delay.

    Args:
        attempt: Current attempt number (starting from 0)
        base_delay: Base delay in seconds
        max_delay: Maximum delay in seconds

    Returns:
        Delay in seconds
    """
    delay = base_delay * (2 ** attempt)
    return min(delay, max_delay)


def jitter(delay: float, jitter_factor: float = 0.1) -> float:
    """Add random jitter to a delay.

    Args:
        delay: Base delay in seconds
        jitter_factor: Jitter as fraction of delay (0-1)

    Returns:
        Delay with jitter
    """
    import random
    jitter_amount = delay * jitter_factor * random.random()
    return delay + jitter_amount