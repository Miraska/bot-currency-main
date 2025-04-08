import logging
import os
from .config import config

def setup_logging() -> logging.Logger:
    """
    Настраивает логирование (в консоль и файл).
    """
    log_level = logging.DEBUG if config.DEBUG_MODE else logging.INFO

    # Создаём папку logs, если не существует
    os.makedirs("logs", exist_ok=True)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(config.LOG_FILE, encoding="utf-8")
        ],
    )
    logger = logging.getLogger(__name__)
    logger.info("Logging configured successfully.")
    return logger
