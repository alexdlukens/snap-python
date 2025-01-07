import logging
import uuid
from pathlib import Path

import pytest

from snap_python.client import SnapClient

BASE_DIR = Path(__file__).resolve().parent.parent
CODE_DIR = BASE_DIR / "src" / "snap_python"
TEST_DIR = BASE_DIR / "tests"
TEST_DATA_DIR = TEST_DIR / "data"

logger = logging.getLogger("snap_python.tests.test_config_endpoints")
logger.setLevel(logging.DEBUG)
logger.handlers.clear()
logger.propagate = True


@pytest.mark.asyncio
async def test_snap_set_and_get_config(module_scope_client: SnapClient):
    # install nextcloud snap (need a snap that supports configuration)
    test_snap = "nextcloud"
    await module_scope_client.snaps.install_snap(test_snap, wait=True)

    try:
        # get configuration
        config_before = await module_scope_client.config.get_configuration(test_snap)
        logger.debug(
            "Get configuration before response\n%s",
            config_before.model_dump_json(indent=4),
        )
        # set new key-value pair
        config_before.result["test-value-1"] = uuid.uuid4().hex

        # set configuration
        response = await module_scope_client.config.set_configuration(
            test_snap, configuration=config_before.result, wait=True
        )
        logger.debug(
            "Set configuration response\n%s", response.model_dump_json(indent=4)
        )

        config_after = await module_scope_client.config.get_configuration(test_snap)
        logger.debug(
            "Get configuration after time response\n%s",
            config_after.model_dump_json(indent=4),
        )
        assert config_before.result == config_after.result
        assert (
            config_before.result["test-value-1"] == config_after.result["test-value-1"]
        )
    finally:
        # remove snap
        await module_scope_client.snaps.remove_snap(test_snap, wait=True)
