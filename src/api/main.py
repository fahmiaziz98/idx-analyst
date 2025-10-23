from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.api.initialize import initialize_vector_store
from src.api.logger import setup_logger
from src.api.middleware import setup_middlewares
from src.api.v1 import routers, websocket
from src.core import settings
from src.models.schemas import ErrorResponse, HealthResponse

logger = setup_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Run on application startup and shutdown
    """
    logger.info("=" * 50)
    logger.info(f"Starting {settings.API_TITLE} v{settings.API_VERSION}")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Docs available at: http://{settings.HOST}:{settings.PORT}/docs")
    logger.info("=" * 50)

    init_success = await initialize_vector_store()
    if not init_success:
        logger.error("Vector store initialization failed. Shutting down application.")
        import sys

        sys.exit(1)
    yield
    logger.info("Shutting down application...")


app = FastAPI(
    title=settings.API_TITLE,
    description=settings.API_DESCRIPTION,
    version=settings.API_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)


# Exception handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Handle validation errors
    """
    logger.warning(f"Validation error: {exc.errors()}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": "Validation Error", "detail": exc.errors(), "body": exc.body},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Global exception handler
    """
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error="Internal Server Error",
            detail=str(exc)
            if settings.ENVIRONMENT == "development"
            else "An unexpected error occurred",
        ).model_dump(),
    )


setup_middlewares(app)


@app.get("/", tags=["Root"])
async def root():
    """
    Root endpoint
    """
    return {
        "message": "Welcome to RAG Chatbot API",
        "version": settings.API_VERSION,
        "description": settings.API_DESCRIPTION,
        "docs": "/docs",
        "health": "/api/v1/health",
        "endpoints": {
            "chat": "/api/v1/chat",
            "stream": "/api/v1/chat/stream",
            "websocket": "/api/v1/ws/chat",
        },
    }


@app.get("/health", response_model=HealthResponse, tags=["Health"], summary="Health check endpoint")
async def health_check():
    """
    Check API health status
    """
    logger.info("Health check requested")
    return HealthResponse(status="healthy", version=settings.API_VERSION)


app.include_router(routers.router, prefix="/api/v1", tags=["Chat-Agent"])
app.include_router(websocket.router, prefix="/api/v1/ws", tags=["WebSocket"])
