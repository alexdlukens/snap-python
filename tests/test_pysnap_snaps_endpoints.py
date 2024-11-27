import asyncio
import logging
from pathlib import Path

import httpx
import pytest

from pysnap.client import SnapClient
from pysnap.schemas.changes import ChangesResponse
from tests.lib.setup_lxd_container import module_scope_container  # noqa: F401

BASE_DIR = Path(__file__).resolve().parent.parent
CODE_DIR = BASE_DIR / "src" / "pysnap"
TEST_DIR = BASE_DIR / "tests"
TEST_DATA_DIR = TEST_DIR / "data"

logger = logging.getLogger("pysnap.tests.test_pysnap_snaps_endpoints")
logger.setLevel(logging.DEBUG)
logger.handlers.clear()
logger.propagate = True


@pytest.fixture
def setup_lxd_client(module_scope_container) -> SnapClient:
    container = module_scope_container
    logger.info(f"Container ID: {container.name}")
    return SnapClient(version="v2", tcp_location="http://127.0.0.1:8181")


@pytest.mark.asyncio
async def test_snap_client_list_snaps(setup_lxd_client: SnapClient):
    logger.debug("Running test_snap_client_list_snaps")
    installed_snaps = []
    try:
        installed_snaps = await setup_lxd_client.snaps.list_installed_snaps()
    except httpx.HTTPStatusError as e:
        pytest.fail(
            f"List installed snaps failed with status code {e.response.status_code}"
        )
    assert len(installed_snaps) == 0


@pytest.mark.asyncio
async def test_snap_client_install_snap_no_wait(setup_lxd_client: SnapClient):
    logger.debug("Running test_snap_client_install_snap")
    response = await setup_lxd_client.snaps.install_snap("hello-world")
    assert response.status_code == 202

    while True:
        changes = await setup_lxd_client.get_changes_by_id(response.change)
        assert changes.status_code == 200
        if changes.result.ready:
            logger.debug("Snap hello-world installed successfully")
            break
        await asyncio.sleep(1.0)

    installed_snaps = await setup_lxd_client.snaps.list_installed_snaps()
    assert len(installed_snaps) == 2
    snap_names = [snap.name for snap in installed_snaps.result]
    assert "hello-world" in snap_names
    assert "core" in snap_names

    logger.debug("Removing the snap now")
    # remove the snap
    removal_response = await setup_lxd_client.snaps.remove_snap(
        "hello-world", purge=True, terminate=True
    )
    assert removal_response.status_code == 202

    while True:
        changes = await setup_lxd_client.get_changes_by_id(removal_response.change)
        if changes.result.ready:
            logger.debug("Snap hello-world removed successfully")
            break
        await asyncio.sleep(1.0)

    installed_snaps = await setup_lxd_client.snaps.list_installed_snaps()
    assert "hello-world" not in [snap.name for snap in installed_snaps.result]


async def test_snap_client_install_with_wait(setup_lxd_client: SnapClient):
    logger.debug("Running test_snap_client_install_with_wait")
    response = await setup_lxd_client.snaps.install_snap("hello-world", wait=True)
    assert isinstance(response, ChangesResponse)
    assert response.status_code == 200

    installed_snaps = await setup_lxd_client.snaps.list_installed_snaps()
    assert "hello-world" in [snap.name for snap in installed_snaps.result]

    logger.debug("Removing the snap now")

    removal_response = await setup_lxd_client.snaps.remove_snap(
        "hello-world", purge=True, terminate=True, wait=True
    )
    assert removal_response.status_code == 200

    installed_snaps = await setup_lxd_client.snaps.list_installed_snaps()
    assert "hello-world" not in [snap.name for snap in installed_snaps.result]


async def test_get_unknown_change(setup_lxd_client: SnapClient):
    logger.debug("Running test_get_unknown_change")

    bad_response = await setup_lxd_client.get_changes_by_id("unknown-change-id")

    assert bad_response.status_code == 404
    assert bad_response.status == "Not Found"
    assert not bad_response.ready
    assert bad_response.type == "error"
