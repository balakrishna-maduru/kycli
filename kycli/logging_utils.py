import logging
import os

from kycli.config import KYCLI_DIR, ensure_dirs


_DEF_LOG_NAME = "kycli"
_DEF_LOG_FILE = "kycli.log"


def get_logger(name=_DEF_LOG_NAME):
    """Return a configured logger that writes to ~/.kycli/kycli.log by default."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    ensure_dirs()
    log_path = os.environ.get("KYCLI_LOG_PATH", os.path.join(KYCLI_DIR, _DEF_LOG_FILE))
    level_name = os.environ.get("KYCLI_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    logger.setLevel(level)
    handler = logging.FileHandler(log_path)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False

    return logger
