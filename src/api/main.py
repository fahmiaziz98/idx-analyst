import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.api.initialize import initialize_vector_store
from src.api.logger import setup_logger
from src.api.middleware import setup_middleware
from src.api.v1.api import api_router
from src.auth.token_blacklist import get_redis_connection, shutdown_redis
from src.core import settings
from src.database.session import engine
from src.vector_db.vectorstore import get_retriever_instance

logger = setup_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager for startup and shutdown tasks.

    Startup:
    - Initialize vector database
    - Connect to Redis
    - Verify database connection
    - Log application info

    Shutdown:
    - Close Redis connections
    - Close database connections
    - Cleanup resources
    """
    # ===== STARTUP =====
    logger.info("=" * 80)
    logger.info(f"🚀 Starting {settings.API_TITLE} v{settings.API_VERSION}")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Debug Mode: {not settings.is_production}")
    logger.info("=" * 80)

    # Initialize VectorDB
    logger.info("Initializing VectorDB...")
    init_success = await initialize_vector_store()
    if not init_success:
        logger.critical("Vector DB Init Failed!")
        raise Exception("Vector DB Init Failed!")

    # Connect to redis
    try:
        logger.info("Connecting to Redis...")
        redis_client = await get_redis_connection()
        await redis_client.ping()
        logger.info("✅ Redis connected")
    except Exception as e:
        logger.error(f"❌ Redis connection failed: {e}")
        if settings.is_production:
            raise RuntimeError("Redis connection failed") from e

    # Verify Database Connection
    try:
        logger.info("Verifying database connection...")
        async with engine.begin() as conn:
            await conn.execute("SELECT 1")
        logger.success("✅ Database connected")
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        if settings.is_production:
            raise RuntimeError("Database connection failed") from e

    logger.info("=" * 80)
    logger.success("🎉 Application startup complete")
    logger.info("=" * 80)

    yield

    # ===== SHUTDOWN =====
    logger.info("=" * 80)
    logger.info("🛑 Shutting down application...")
    logger.info("=" * 80)

    # Close Redis connections
    try:
        await shutdown_redis()
        logger.success("✅ Redis connections closed")
    except Exception as e:
        logger.error(f"❌ Error closing Redis: {e}")

    # Close Database connections
    try:
        await engine.dispose()
        logger.success("✅ Database connections closed")
    except Exception as e:
        logger.error(f"❌ Error closing Database: {e}")

    logger.info("=" * 80)
    logger.success("👋 Application shutdown complete")
    logger.info("=" * 80)


# Create FastAPI application
app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    description=settings.API_DESCRIPTION,
    lifespan=lifespan,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    openapi_url="/openapi.json" if not settings.is_production else None,
)

# Setup middleware
setup_middleware(app)


# ===== EXCEPTION HANDLERS =====
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Handle Pydantic validation errors.

    Returns structured error response with validation details.
    """
    error_details = exc.errors()

    logger.warning(f"Validation error on {request.method} {request.url.path}: {error_details}")

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "validation_error",
            "message": "Request validation failed",
            "details": error_details,
            "path": str(request.url.path),
        },
    )


@app.exception_handler(Exception)
async def global_handler(request: Request, exc: Exception):
    """
    Global exception handler for uncaught errors.

    Logs the exception and returns a 500 JSON response.
    """
    # Generate unique error ID
    error_id = str(uuid.uuid4())

    #  Log error with full context
    logger.error(
        f"Unhandled exception [ID: {error_id}] on {request.method} {request.url.path}",
        exc_info=True,
    )

    # Determine error message based on environment
    if settings.is_production:
        error_detail = "An unexpected error occurred. Please try again later."
    else:
        error_detail = str(exc)

    response_content = {
        "error": "internal_server_error",
        "message": error_detail,
        "error_id": error_id,
        "path": str(request.url.path),
    }

    # Include exception type in development
    if not settings.is_production:
        response_content["exception_type"] = type(exc).__name__

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=response_content,
    )


@app.get("/health", tags=["Health"])
async def health_check():
    """
    Comprehensive health check endpoint.

    Checks:
    - Application status
    - Database connectivity
    - Redis connectivity
    - Vector database connectivity

    Returns:
        Health status with component checks
    """
    checks = {
        "application": "healthy",
        "database": "unknown",
        "redis": "unknown",
        "vector_db": "unknown",
    }

    # Check Database
    try:
        async with engine.begin() as conn:
            await conn.execute("SELECT 1")
        checks["database"] = "healthy"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        checks["database"] = "unhealthy"

    # Check Redis
    try:
        redis_client = await get_redis_connection()
        await redis_client.ping()
        checks["redis"] = "healthy"
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        checks["redis"] = "unhealthy"

    # Check Vector DB
    try:
        retriever = get_retriever_instance()
        if retriever.client:
            await retriever.client.get_collections()
            checks["vector_db"] = "healthy"
        else:
            checks["vector_db"] = "unhealthy"
    except Exception as e:
        logger.error(f"Vector DB health check failed: {e}")
        checks["vector_db"] = "unhealthy"

    # Determine overall health
    is_healthy = all(status == "healthy" for status in checks.values())

    status_code = status.HTTP_200_OK if is_healthy else status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "healthy" if is_healthy else "degraded",
            "version": settings.API_VERSION,
            "environment": settings.ENVIRONMENT,
            "checks": checks,
        },
    )


@app.get("/", tags=["Root"])
async def root():
    """
    Root endpoint with API information.
    """
    return {
        "name": settings.API_TITLE,
        "version": settings.API_VERSION,
        "environment": settings.ENVIRONMENT,
        "docs": "/docs" if not settings.is_production else None,
        "health": "/health",
    }


app.include_router(api_router, prefix="/api/v1")
