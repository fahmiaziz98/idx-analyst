import time
import secrets
from collections.abc import Callable

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from src.core import settings

limiter = Limiter(key_func=get_remote_address)


class SecurityHeadersMiddleware:
    """
    Add security headers to all responses.

    Headers added:
    - X-Frame-Options: Prevent clickjacking
    - X-Content-Type-Options: Prevent MIME sniffing
    - X-XSS-Protection: Enable XSS filter
    - Strict-Transport-Security (HSTS): Force HTTPS (production only)
    - Content-Security-Policy: Restrict resource loading
    - Referrer-Policy: Control referrer information
    - Permissions-Policy: Control browser features
    """

    def __init__(self, app: FastAPI):
        self.app = app

    async def __call__(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Relaxed CSP for Swagger UI compatibility
        # Allow 'unsafe-inline' for styles/scripts and cdn.jsdelivr.net which FastAPI uses by default
        csp_policy = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data: https://fastapi.tiangolo.com; "
            "connect-src 'self' https://accounts.google.com"
        )
        response.headers["Content-Security-Policy"] = csp_policy

        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=()"

        #  HSTS (production only)
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = (
                f"max-age={settings.HSTS_MAX_AGE}; includeSubDomains; preload"
            )

        return response


class MetricsMiddleware:
    """
    Request latency logging and metrics middleware.

    Logs:
    - Request method and path
    - Response status code
    - Processing time
    - Client IP address
    """

    def __init__(self, app: FastAPI):
        self.app = app

    async def __call__(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()
        client_ip = request.client.host if request.client else "unknown"

        try:
            response = await call_next(request)
        except Exception as e:
            logger.error(f"Request failed for {client_ip}: {e}")
            raise

        process_time = time.time() - start_time

        logger.info(
            f"{request.method} {request.url.path} "
            f"| Status: {response.status_code} "
            f"| Latency: {process_time:.4f}s"
            f"| Client IP: {client_ip}"
        )

        # Add custom headers
        response.headers["X-Process-Time"] = f"{process_time:.4f}"
        response.headers["X-Request-ID"] = request.headers.get("X-Request-ID", "not-set")

        return response


class CSRFProtectionMiddleware:
    """
    Double Submit Cookie CSRF Protection.
    How it works:
    1. Server generates random CSRF token
    2. Token stored in cookie (SameSite protection)
    3. Client reads cookie and sends token in header
    4. Server validates cookie matches header

    Why this works:
    - Attacker cannot read cookie due to Same-Origin Policy
    - Attacker cannot set custom headers in CSRF attack
    - Even if attacker guesses token, they can't set the cookie

    Protection against:
    - CSRF attacks via forms
    - CSRF attacks via AJAX
    - Subdomain attacks (with proper SameSite)

    Does NOT protect against:
    - XSS attacks (use Content Security Policy)
    - Man-in-the-middle (use HTTPS)
    """

    def __init__(self, app: FastAPI):
        self.app = app

        # Paths that don't require CSRF protection
        self.exempt_paths = [
            "/api/v1/auth/callback",  # OAuth callback
            "/api/v1/auth/login",  # OAuth initiation
            "/health",  # Health check
            "/docs",  # API docs
            "/openapi.json",  # OpenAPI spec
        ]

        # Only protect state-changing methods
        self.protected_methods = ["POST", "PUT", "DELETE", "PATCH"]

    async def __call__(self, request: Request, call_next: Callable) -> Response:
        # Check if path is exempt
        is_exempt = any(request.url.path.startswith(path) for path in self.exempt_paths)

        # Check if method needs protection
        needs_protection = request.method in self.protected_methods and not is_exempt

        if needs_protection:
            csrf_cookie = request.cookies.get("csrf_token")
            csrf_header = request.headers.get("X-CSRF-Token")

            # Verify both exist
            if not csrf_cookie or not csrf_header:
                logger.warning(
                    f"⚠️ CSRF token missing: "
                    f"cookie={bool(csrf_cookie)}, header={bool(csrf_header)} "
                    f"from {request.client.host if request.client else 'unknown'}"
                )
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={
                        "error": "csrf_token_missing",
                        "message": "CSRF token required for this operation",
                    },
                )

            if not secrets.compare_digest(csrf_cookie, csrf_header):
                logger.warning(
                    f"⚠️ CSRF token mismatch: "
                    f"cookie={csrf_cookie}, header={csrf_header} "
                    f"from {request.client.host if request.client else 'unknown'}"
                )
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={
                        "error": "csrf_token_mismatch",
                        "message": "CSRF token mismatch for this operation",
                    },
                )
            logger.debug(f"CSRF token validated for {request.method} {request.url.path}")

        response = await call_next(request)

        # Set CSRF token cookie if not present
        if "csrf_token" not in request.cookies:
            csrf_token = secrets.token_urlsafe(32)
            response.set_cookie(
                key="csrf_token",
                value=csrf_token,
                httponly=False,  # Must be readable by JavaScript
                secure=settings.COOKIE_SECURE,
                samesite=settings.COOKIE_SAMESITE,
                max_age=86400,  # 24 hours
                path="/",
            )
            logger.debug(f"New CSRF token generated: {csrf_token[:8]}...")

        return response


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """
    Custom handler for rate limit exceeded errors.

    Returns user-friendly JSON response with retry information.
    """
    return JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit_exceeded",
            "message": "Too many requests. Please try again later.",
            "detail": str(exc.detail),
            "retry_after": "60 seconds",
        },
        headers={"Retry-After": "60"},
    )


def setup_middleware(app: FastAPI):
    """
    Configure all middleware for the FastAPI application.

    Middleware order (applied bottom-to-top):
    1. Trusted Host (production only)
    2. CORS
    3. Session
    4. Security Headers
    5. Metrics/Logging
    6. Rate Limiting

    Args:
        app: FastAPI application instance
    """

    # Trusted Host (production only)
    if settings.is_production:
        allowed_hosts = []

        # Extract domain from allowed redirect domain
        for domain in settings.ALLOWED_REDIRECT_DOMAINS:
            allowed_hosts.append(domain)
            allowed_hosts.append(f"*.{domain}")  # allow sub domain

        app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
        logger.info(f"Trusted Host Middleware enabled: {allowed_hosts}")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
        allow_headers=["*"],
        expose_headers=["X-Process-Time", "X-Request-ID"],
        max_age=3600 if settings.is_production else 0,
    )
    logger.info(f"CORS Middleware configured: {settings.ALLOWED_ORIGINS}")

    # 3. Session Middleware
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.SESSION_SECRET,
        max_age=settings.SESSION_MAX_AGE,
        same_site=settings.COOKIE_SAMESITE,
        https_only=settings.COOKIE_SECURE,
    )
    logger.info("Session Middleware configured")

    # 4. Security Headers Middleware
    if settings.ENABLE_SECURITY_HEADERS:
        app.middleware("http")(SecurityHeadersMiddleware(app))
        logger.info("Security Headers Middleware enabled")

    # 5. CSRF Protection Middleware
    if settings.ENABLE_CRF_PROTECTION:
        app.middleware("http")(CSRFProtectionMiddleware(app))
        logger.info("CSRF Protection Middleware enabled")

    # 6. Metrics Middleware
    app.middleware("http")(MetricsMiddleware(app))
    logger.info("Metrics Middleware enabled")

    # 7. Rate Limiting
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    logger.info("Rate Limiting configured")

    logger.success("All middleware configured successfully")
