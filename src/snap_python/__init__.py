import logging
import os

log_level = os.getenv("SNAP_PYTHON_LOG_LEVEL", "INFO").upper()
numeric_level = getattr(logging, log_level, logging.INFO)
logger = logging.getLogger("snap_python")
logger.setLevel(numeric_level)
