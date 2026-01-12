import functools
import time
from typing import Callable, Any

from loguru import logger


def format_time(seconds: float) -> str:
    """
    Format time in human-readable format.
    
    Args:
        seconds: Time in seconds
    
    Returns:
        Formatted string: "1.23s" for seconds, "2.34m" for minutes
    """
    if seconds >= 60:
        return f"{seconds / 60:.2f}m"
    return f"{seconds:.2f}s"


def measure_time(func: Callable) -> Callable:
    """
    Decorator to measure and log execution time of synchronous functions.
    
    Returns:
        Tuple of (result, execution_time_seconds)
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> tuple[Any, float]:
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()
        execution_time = end_time - start_time
        logger.info(f"Function '{func.__name__}' took {format_time(execution_time)}")
        return result, execution_time
    return wrapper


def measure_time_async(func: Callable) -> Callable:
    """
    Decorator to measure and log execution time of async functions.
    
    Returns:
        Tuple of (result, execution_time_seconds)
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs) -> tuple[Any, float]:
        start_time = time.perf_counter()
        result = await func(*args, **kwargs)
        end_time = time.perf_counter()
        execution_time = end_time - start_time
        logger.info(f"Async function '{func.__name__}' took {format_time(execution_time)}")
        return result, execution_time
    return wrapper


class Timer:
    """
    Context manager for measuring execution time.
    
    Example:
        with Timer() as t:
            do_something()
        print(f"Took {t.elapsed_str}")
    """
    
    def __init__(self):
        self.start_time: float = 0
        self.end_time: float = 0
        self.elapsed: float = 0
    
    def __enter__(self) -> "Timer":
        self.start_time = time.perf_counter()
        return self
    
    def __exit__(self, *args) -> None:
        self.end_time = time.perf_counter()
        self.elapsed = self.end_time - self.start_time
    
    @property
    def elapsed_str(self) -> str:
        """Get formatted elapsed time string."""
        return format_time(self.elapsed)
