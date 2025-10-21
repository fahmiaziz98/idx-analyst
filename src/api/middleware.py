import time

from fastapi import HTTPException, Request
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware


class LoggingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, throttle_rate: int = 60):
        super().__init__(app)
        self.throttle_rate = throttle_rate
        self.request_log = {}

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host
        now = time.time()

        self.request_log = {
            ip: [ts for ts in times if ts > now - 60] for ip, times in self.request_log.items()
        }

        ip_history = self.request_log.get(client_ip, [])
        if len(ip_history) >= self.throttle_rate:
            raise HTTPException(status_code=429, detail="Too many requests")

        ip_history.append(now)
        self.request_log[client_ip] = ip_history

        start = time.time()
        try:
            response = await call_next(request)
        except Exception as e:
            logger.exception(f"Error handling request {request.method} {request.url.path}")
            raise e

        process_time = time.time() - start

        logger.info(
            f"{request.method} {request.url.path} "
            f"→ {response.status_code} | {process_time:.3f}s | from {client_ip}"
        )

        return response
