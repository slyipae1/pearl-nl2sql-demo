import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional

DEFAULT_LOG_LEVEL = "INFO"

def setup_root_logger(log_level: str = DEFAULT_LOG_LEVEL, log_path: Optional[Path] = None, debug_full_prompts: bool = False):
    level = getattr(logging, log_level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(level)
    fmt = "[%(asctime)s] %(levelname)-7s [%(name)s] %(threadName)s %(message)s"
    ch.setFormatter(logging.Formatter(fmt))
    root.handlers = []
    root.addHandler(ch)

    # File handler (rotating)
    if log_path:
        try:
            log_path = Path(log_path)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            fh = logging.handlers.RotatingFileHandler(str(log_path), maxBytes=10 * 1024 * 1024, backupCount=5, encoding='utf-8')
            fh.setLevel(logging.INFO)
            fh.setFormatter(logging.Formatter(fmt))
            root.addHandler(fh)
        except Exception:
            root.exception("Failed to create file handler for logs: %s", log_path)

    # Silence verbose libraries unless DEBUG
    if level > logging.DEBUG:
        for noisy in ("sqlalchemy", "urllib3", "httpx", "asyncio"):
            logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.getLogger(__name__).debug("Logging initialized", extra={"debug_full_prompts": debug_full_prompts})

def get_logger(name: str):
    return logging.getLogger(name)
