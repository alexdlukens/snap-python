# Content for /pysnap/tests/__init__.py
import logging

logger = logging.getLogger("pysnap.tests")
logger.setLevel(logging.DEBUG)
logger.handlers.clear()
logger.addHandler(logging.StreamHandler())
logger.addHandler(logging.FileHandler("pysnap_testing.log"))
