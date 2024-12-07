import logging
import uuid
from pathlib import Path

import pytest

from snap_python.client import SnapClient
from tests.lib.setup_lxd_container import module_scope_container  # noqa: F401

BASE_DIR = Path(__file__).resolve().parent.parent
CODE_DIR = BASE_DIR / "src" / "snap_python"
TEST_DIR = BASE_DIR / "tests"
TEST_DATA_DIR = TEST_DIR / "data"

logger = logging.getLogger("snap_python.tests.test_config_endpoints")
logger.setLevel(logging.DEBUG)
logger.handlers.clear()
logger.propagate = True


@pytest.fixture
def setup_lxd_client(module_scope_container) -> SnapClient:
    container = module_scope_container
    logger.info("Container ID: %s", container.name)
    return SnapClient(version="v2", tcp_location="http://127.0.0.1:8181")


@pytest.mark.asyncio
async def test_snap_set_and_get_config(setup_lxd_client: SnapClient):
    # install nextcloud snap (need a snap that supports configuration)
    test_snap = "nextcloud"
    await setup_lxd_client.snaps.install_snap(test_snap, wait=True)

    try:
        # get configuration
        config_before = await setup_lxd_client.config.get_configuration(test_snap)
        logger.debug(
            "Get configuration before response\n%s",
            config_before.model_dump_json(indent=4),
        )
        # set new key-value pair
        config_before.result["test-value-1"] = uuid.uuid4().hex

        # set configuration
        response = await setup_lxd_client.config.set_configuration(
            test_snap, configuration=config_before.result, wait=True
        )
        logger.debug(
            "Set configuration response\n%s", response.model_dump_json(indent=4)
        )

        config_after = await setup_lxd_client.config.get_configuration(test_snap)
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
        await setup_lxd_client.snaps.remove_snap(test_snap, wait=True)
