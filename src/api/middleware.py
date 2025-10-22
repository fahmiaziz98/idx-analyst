import time

from fastapi import HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware to limit the number of requests from a single IP address.
    Attributes:
        throttle_rate (int): Maximum number of requests allowed within the time window.
        window_seconds (int): Time window in seconds
    """

    def __init__(self, app, throttle_rate: int = 60, window_seconds: int = 60):
        super().__init__(app)
        self.throttle_rate = throttle_rate
        self.window_seconds = window_seconds
        self.request_log: dict[str, list[float]] = {}

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()

        self.request_log = {
            ip: [ts for ts in times if ts > now - self.window_seconds]
            for ip, times in self.request_log.items()
        }

        ip_history = self.request_log.get(client_ip, [])

        if len(ip_history) >= self.throttle_rate:
            logger.warning(f"[429] Too many requests from {client_ip}")
            raise HTTPException(
                status_code=429,
                detail=f"Too many requests from {client_ip}. Try again later.",
            )

        ip_history.append(now)
        self.request_log[client_ip] = ip_history

        start_time = time.time()
        try:
            response = await call_next(request)
        except Exception as e:
            logger.exception(f"Error handling request {request.method} {request.url.path}: {e}")
            raise e

        process_time = time.time() - start_time

        logger.info(
            f"{request.method} {request.url.path} "
            f"→ {response.status_code} | {process_time:.3f}s | from {client_ip}"
        )

        response.headers["X-RateLimit-Limit"] = str(self.throttle_rate)
        response.headers["X-RateLimit-Remaining"] = str(
            max(0, self.throttle_rate - len(ip_history))
        )
        response.headers["X-RateLimit-Reset"] = str(self.window_seconds)

        return response


def setup_cors(app):
    """
    Setup CORS middleware
    """
    from src.core import settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Process-Time"],
    )

    logger.info(f"CORS configured with origins: {settings.allowed_origins_list}")


def setup_middlewares(app):
    """
    Setup all middlewares
    """
    app.add_middleware(RateLimitMiddleware, throttle_rate=60, window_seconds=60)
    setup_cors(app)

    logger.info("All middlewares configured")
