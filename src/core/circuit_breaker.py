import asyncio
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional

from loguru import logger


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing - reject immediately
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""

    failure_threshold: int = 5  # Failures before opening
    success_threshold: int = 2  # Successes to close from half-open
    timeout: int = 60  # Seconds before trying half-open
    expected_exception: type[Exception] = Exception


@dataclass
class CircuitBreakerStats:
    """Statistics for monitoring."""

    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None


class CircuitBreakerError(Exception):
    """Raised when circuit breaker is open."""

    pass


class CircuitBreaker:
    """
    Circuit breaker for external service calls.

    Usage:
        breaker = CircuitBreaker(name="embedding_api")

        @breaker.call
        async def call_embedding_api():
            return await client.get_embeddings(...)

        # Or decorator style:
        @breaker.protected
        async def my_function():
            ...
    """

    def __init__(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None,
    ):
        """
        Initialize circuit breaker.

        Args:
            name: Identifier for logging
            config: Configuration object
        """
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitState.CLOSED
        self.stats = CircuitBreakerStats()

        self._failure_count = 0
        self._success_count = 0
        self._last_attempt_time: Optional[float] = None
        self._lock = asyncio.Lock()

        logger.info(f"Circuit breaker '{name}' initialized in {self.state.value} state")

    @property
    def is_closed(self) -> bool:
        """Check if circuit is closed (normal operation)."""
        return self.state == CircuitState.CLOSED

    @property
    def is_open(self) -> bool:
        """Check if circuit is open (failing)."""
        return self.state == CircuitState.OPEN

    @property
    def is_half_open(self) -> bool:
        """Check if circuit is half-open (testing)."""
        return self.state == CircuitState.HALF_OPEN

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection.

        Args:
            func: Async function to call
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Function result

        Raises:
            CircuitBreakerError: If circuit is open
            Exception: Original exception from function
        """
        async with self._lock:
            self.stats.total_calls += 1

            # Check if circuit should transition to half-open
            if self.is_open:
                if self._should_attempt_reset():
                    logger.info(f"Circuit breaker '{self.name}' transitioning to HALF_OPEN")
                    self.state = CircuitState.HALF_OPEN
                    self._success_count = 0
                else:
                    # Circuit still open - reject immediately
                    self.stats.rejected_calls += 1
                    time_remaining = self._get_time_until_retry()
                    logger.warning(
                        f"Circuit breaker '{self.name}' is OPEN. "
                        f"Retry in {time_remaining:.0f}s"
                    )
                    raise CircuitBreakerError(
                        f"Circuit breaker '{self.name}' is open. "
                        f"Service unavailable. Retry in {time_remaining:.0f}s"
                    )

        # Execute the function
        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result

        except self.config.expected_exception as e:
            await self._on_failure()
            raise e

    def protected(self, func: Callable) -> Callable:
        """
        Decorator to protect async functions with circuit breaker.

        Usage:
            breaker = CircuitBreaker("my_api")

            @breaker.protected
            async def call_api():
                return await client.call()
        """

        async def wrapper(*args, **kwargs):
            return await self.call(func, *args, **kwargs)

        return wrapper

    async def _on_success(self):
        """Handle successful call."""
        async with self._lock:
            self.stats.successful_calls += 1
            self.stats.last_success_time = time.time()
            self._failure_count = 0

            if self.is_half_open:
                self._success_count += 1
                logger.debug(
                    f"Circuit breaker '{self.name}': "
                    f"{self._success_count}/{self.config.success_threshold} successes"
                )

                if self._success_count >= self.config.success_threshold:
                    logger.info(f"Circuit breaker '{self.name}' closing - service recovered")
                    self.state = CircuitState.CLOSED
                    self._success_count = 0

    async def _on_failure(self):
        """Handle failed call."""
        async with self._lock:
            self.stats.failed_calls += 1
            self.stats.last_failure_time = time.time()
            self._failure_count += 1
            self._last_attempt_time = time.time()

            logger.warning(
                f"Circuit breaker '{self.name}': "
                f"{self._failure_count}/{self.config.failure_threshold} failures"
            )

            if self.is_half_open:
                # Failed during recovery - reopen circuit
                logger.error(f"Circuit breaker '{self.name}' reopening - service still failing")
                self.state = CircuitState.OPEN
                self._success_count = 0

            elif self._failure_count >= self.config.failure_threshold:
                # Too many failures - open circuit
                logger.error(
                    f"Circuit breaker '{self.name}' opening after "
                    f"{self._failure_count} failures"
                )
                self.state = CircuitState.OPEN

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if not self._last_attempt_time:
            return True

        elapsed = time.time() - self._last_attempt_time
        return elapsed >= self.config.timeout

    def _get_time_until_retry(self) -> float:
        """Get seconds until retry is allowed."""
        if not self._last_attempt_time:
            return 0

        elapsed = time.time() - self._last_attempt_time
        return max(0, self.config.timeout - elapsed)

    def reset(self):
        """Manually reset circuit breaker to closed state."""
        with self._lock:
            logger.info(f"Circuit breaker '{self.name}' manually reset to CLOSED")
            self.state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0

    def get_stats(self) -> dict[str, Any]:
        """Get current statistics."""
        return {
            "name": self.name,
            "state": self.state.value,
            "total_calls": self.stats.total_calls,
            "successful_calls": self.stats.successful_calls,
            "failed_calls": self.stats.failed_calls,
            "rejected_calls": self.stats.rejected_calls,
            "failure_rate": (
                self.stats.failed_calls / self.stats.total_calls
                if self.stats.total_calls > 0
                else 0
            ),
            "last_failure": (
                time.time() - self.stats.last_failure_time
                if self.stats.last_failure_time
                else None
            ),
        }


class CircuitBreakerRegistry:
    """
    Global registry for managing multiple circuit breakers.

    Usage:
        registry = CircuitBreakerRegistry()
        embedding_breaker = registry.get_or_create("embedding_api")
        rerank_breaker = registry.get_or_create("rerank_api")
    """

    def __init__(self):
        self._breakers: dict[str, CircuitBreaker] = {}

    def get_or_create(
        self, name: str, config: Optional[CircuitBreakerConfig] = None
    ) -> CircuitBreaker:
        """Get existing breaker or create new one."""
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(name, config)
        return self._breakers[name]

    def get(self, name: str) -> Optional[CircuitBreaker]:
        """Get breaker by name."""
        return self._breakers.get(name)

    def get_all_stats(self) -> dict[str, dict]:
        """Get statistics for all breakers."""
        return {name: breaker.get_stats() for name, breaker in self._breakers.items()}

    def reset_all(self):
        """Reset all circuit breakers."""
        for breaker in self._breakers.values():
            breaker.reset()


# Global registry instance
circuit_breaker_registry = CircuitBreakerRegistry()


# Convenience function
def get_circuit_breaker(
    name: str, config: Optional[CircuitBreakerConfig] = None
) -> CircuitBreaker:
    """
    Get or create a circuit breaker from global registry.

    Args:
        name: Breaker identifier
        config: Optional configuration

    Returns:
        CircuitBreaker instance
    """
    return circuit_breaker_registry.get_or_create(name, config)