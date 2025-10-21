import os
import sys

from loguru import logger

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
    "<level>{level:<8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>",
    level="INFO",
    colorize=True,
    enqueue=True,  # thread-safe
)
logger.add(
    f"{LOG_DIR}/app_{{time:YYYY-MM-DD}}.log",
    rotation="00:00",
    retention="7 days",
    compression="zip",
    level="INFO",
    enqueue=True,
    format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {message}",
)


def configure_global_logger():
    def exception_handler(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.exception("Uncaught exception:", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = exception_handler


configure_global_logger()
