from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.api.initialize import initialize_vector_store
from src.api.logger import setup_logger
from src.api.middleware import limiter, setup_middleware
from src.api.v1.api import api_router
from src.core import settings
from src.schemas.common import ErrorResponse, HealthResponse

logger = setup_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager.

    Performs startup and shutdown tasks for the FastAPI app.

    Args:
    app (FastAPI): The FastAPI application instance.

    Yields
        None: The context manager yields control to the application.
    """
    # Startup
    logger.info(f"Starting {settings.API_TITLE}...")
    init_success = await initialize_vector_store()
    if not init_success:
        logger.critical("Vector DB Init Failed!")

    yield

    logger.info("Shutting down...")


app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    lifespan=lifespan,
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,  # Hide docs in prod
)

setup_middleware(app)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    """
    Handle FastAPI request validation errors.

    Returns a JSON response with status code 422 and error details.
    """
    error_details = exc.errors()
    return JSONResponse(
        status_code=422,
        content={
            "error": "Validation Error",
            "detail": str(error_details),
            "validation_errors": error_details,
        },
    )


@app.exception_handler(Exception)
async def global_handler(request: Request, exc: Exception):
    """
    Global exception handler for uncaught errors.

    Logs the exception and returns a 500 JSON response.
    """
    logger.error(f"Global Error: {exc}", exc_info=True)

    error_detail = str(exc) if settings.ENVIRONMENT != "production" else "Internal Server Error"

    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="Internal Server Error",
            detail=error_detail,
        ).model_dump(mode="json"),
    )


@app.get("/")
@limiter.limit("3/minutes")
async def root(request: Request):
    """Root endpoint."""
    return HealthResponse(
        name=settings.API_TITLE,
        version=settings.API_VERSION,
        docs="/docs",
    )


app.include_router(api_router, prefix="/api/v1")
