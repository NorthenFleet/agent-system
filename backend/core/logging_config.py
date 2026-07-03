import logging
import os
import sys
from datetime import datetime
from typing import Optional


LOG_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s"
)

LOG_FORMAT_DETAILED = (
    "%(asctime)s | %(levelname)-8s | %(name)-20s | %(module)s:%(lineno)d | %(message)s"
)

LOG_LEVEL_MAP = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
}


class ColorFormatter(logging.Formatter):
    COLORS = {
        logging.DEBUG: "\033[94m",
        logging.INFO: "\033[92m",
        logging.WARNING: "\033[93m",
        logging.ERROR: "\033[91m",
        logging.CRITICAL: "\033[95m",
    }
    RESET = "\033[0m"

    def format(self, record):
        level_color = self.COLORS.get(record.levelno, "")
        record.levelname = f"{level_color}{record.levelname}{self.RESET}"
        return super().format(record)


def configure_logging(
    level: str = "info",
    log_file: Optional[str] = None,
    console_output: bool = True,
    file_output: bool = True,
    detailed: bool = False,
) -> logging.Logger:
    root_logger = logging.getLogger()
    root_logger.setLevel(LOG_LEVEL_MAP.get(level.lower(), logging.INFO))
    root_logger.handlers.clear()

    formatter = ColorFormatter(LOG_FORMAT_DETAILED if detailed else LOG_FORMAT)

    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    if file_output and log_file:
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT_DETAILED))
        root_logger.addHandler(file_handler)

    return root_logger


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def setup_app_logging() -> None:
    env_level = os.getenv("LOG_LEVEL", "info")
    env_log_dir = os.getenv("LOG_DIR", "logs")
    timestamp = datetime.now().strftime("%Y%m%d")
    log_file = os.path.join(env_log_dir, f"app-{timestamp}.log")

    configure_logging(
        level=env_level,
        log_file=log_file,
        console_output=True,
        file_output=True,
        detailed=env_level == "debug",
    )

    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("fastapi").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)