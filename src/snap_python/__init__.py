import logging
import os

log_level = os.getenv("SNAP_PYTHON_LOG_LEVEL", "DEBUG").upper()
numeric_level = getattr(logging, log_level, logging.DEBUG)
logger = logging.getLogger("snap_python")
logger.setLevel(numeric_level)

ch = logging.StreamHandler()
ch.setLevel(numeric_level)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
ch.setFormatter(formatter)
logger.addHandler(ch)

fh = logging.FileHandler("snap_python.log")
fh.setLevel(numeric_level)
fh.setFormatter(formatter)
logger.addHandler(fh)
