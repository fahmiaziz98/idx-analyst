from fastapi import FastAPI
from .logger import logger
from .middleware import LoggingMiddleware

app = FastAPI(title="My App with Loguru")

# Tambahkan middleware
app.add_middleware(LoggingMiddleware)

@app.get("/")
async def root():
    logger.info("Home endpoint accessed")
    return {"message": "Hello World"}
