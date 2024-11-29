# Content for /snap_python/tests/__init__.py
import logging

logger = logging.getLogger("snap_python.tests")
logger.setLevel(logging.DEBUG)
logger.handlers.clear()
logger.addHandler(logging.StreamHandler())
logger.addHandler(logging.FileHandler("snap_python_testing.log"))
