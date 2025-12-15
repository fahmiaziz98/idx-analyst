import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src.core import settings

limiter = Limiter(key_func=get_remote_address)


class MetricsMiddleware:
    """
    Simple middleware that logs request latency and adds a custom header.

    The middleware records the time taken to process each HTTP request,
    logs the method, path, status code, and latency, and injects an
    ``X-Process-Time`` header into the response.  It can be extended to
    export metrics to Prometheus or another monitoring system.
    """

    async def __call__(self, request: Request, call_next):
        start_time = time.time()

        try:
            response = await call_next(request)
        except Exception as e:
            raise e

        process_time = time.time() - start_time

        logger.info(
            f"{request.method} {request.url.path} "
            f"| Status: {response.status_code} "
            f"| Latency: {process_time:.4f}s"
        )

        response.headers["X-Process-Time"] = str(process_time)
        return response


def setup_middleware(app: FastAPI):
    """
    Register CORS, rate‑limiting, and metrics middleware on the FastAPI app.

    Parameters

    app : FastAPI
        The FastAPI application instance to configure.

    The function adds:
    * CORS middleware with origins from ``settings.allowed_origins_list``.
    * The custom ``MetricsMiddleware`` for latency logging.
    * SlowAPI rate‑limiting middleware and its exception handler.
    """
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    app.middleware("http")(MetricsMiddleware())

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    from starlette.middleware.sessions import SessionMiddleware

    app.add_middleware(SessionMiddleware, secret_key=settings.JWT_SECRET)

    logger.info("Middlewares (CORS, SlowAPI, Metrics, Session) configured.")
