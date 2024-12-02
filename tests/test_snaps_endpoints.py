import asyncio
import logging
from pathlib import Path

import httpx
import pytest

from snap_python.client import SnapClient
from snap_python.schemas.changes import ChangesResponse
from snap_python.schemas.common import AsyncResponse, BaseErrorResult
from tests.lib.setup_lxd_container import module_scope_container  # noqa: F401

BASE_DIR = Path(__file__).resolve().parent.parent
CODE_DIR = BASE_DIR / "src" / "snap_python"
TEST_DIR = BASE_DIR / "tests"
TEST_DATA_DIR = TEST_DIR / "data"

logger = logging.getLogger("snap_python.tests.test_snap_python_snaps_endpoints")
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
    assert await setup_lxd_client.snaps.is_snap_installed("hello-world") is True
    installed_snaps = await setup_lxd_client.snaps.list_installed_snaps()
    assert "hello-world" in [snap.name for snap in installed_snaps.result]

    logger.debug("Removing the snap now")

    removal_response = await setup_lxd_client.snaps.remove_snap(
        "hello-world", purge=True, terminate=True, wait=True
    )
    assert removal_response.status_code == 200

    installed_snaps = await setup_lxd_client.snaps.list_installed_snaps()
    assert "hello-world" not in [snap.name for snap in installed_snaps.result]
    assert await setup_lxd_client.snaps.is_snap_installed("hello-world") is False


async def test_get_unknown_change(setup_lxd_client: SnapClient):
    logger.debug("Running test_get_unknown_change")

    bad_response = await setup_lxd_client.get_changes_by_id("unknown-change-id")

    assert bad_response.status_code == 404
    assert bad_response.status == "Not Found"
    assert isinstance(bad_response.result, BaseErrorResult)
    assert bad_response.type == "error"


async def test_install_specific_snap_revision_channel(setup_lxd_client: SnapClient):
    logger.debug("Running test_install_specific_snap_revision_channel")
    response = await setup_lxd_client.snaps.install_snap(
        "usconstitution", channel="latest/edge", revision=96, wait=True
    )
    assert isinstance(response, ChangesResponse)
    assert response.status_code == 200

    installed_snaps = await setup_lxd_client.snaps.list_installed_snaps()
    assert "usconstitution" in [snap.name for snap in installed_snaps.result]

    constitution_snap = [
        snap for snap in installed_snaps.result if snap.name == "usconstitution"
    ][0]
    assert constitution_snap.revision == "96"
    assert constitution_snap.channel == "latest/edge"

    removal_response = await setup_lxd_client.snaps.remove_snap(
        "usconstitution", purge=True, terminate=True, wait=True
    )
    assert removal_response.status_code == 200

    installed_snaps = await setup_lxd_client.snaps.list_installed_snaps()
    assert "usconstitution" not in [snap.name for snap in installed_snaps.result]


async def test_get_snap_info(setup_lxd_client: SnapClient):
    logger.debug("Running test_get_snap_info")

    # install hello-world snap
    response = await setup_lxd_client.snaps.install_snap("hello-world", wait=True)

    # ensure snap shows up in list_installed_snaps
    installed_snaps = await setup_lxd_client.snaps.list_installed_snaps()
    assert "hello-world" in [snap.name for snap in installed_snaps.result]

    # ensure snap info can be retrieved using get_snap_info
    snap_info = await setup_lxd_client.snaps.get_snap_info("hello-world")
    assert snap_info.status_code == 200

    # ensure snap info is identical to item in list_installed_snaps
    snap_info = snap_info.result
    snap = [snap for snap in installed_snaps.result if snap.name == "hello-world"][0]

    # remove snap
    removal_response = await setup_lxd_client.snaps.remove_snap(
        "hello-world", purge=True, terminate=True, wait=True
    )

    assert snap_info == snap


async def test_install_snap_async_generator(setup_lxd_client: SnapClient):
    logger.debug("Running test_install_snap_async_generator")

    async_install_response: AsyncResponse = await setup_lxd_client.snaps.install_snap(
        "hello-world", wait=False
    )

    count = 0
    async for change in setup_lxd_client.get_changes_by_id_generator(
        async_install_response.change
    ):
        assert isinstance(change, ChangesResponse)
        if change.ready:
            break
        count += 1
        await asyncio.sleep(1.0)
        if count > 90:
            pytest.fail(
                f"Snap installation took longer than expected (90 sec).\n{change.model_dump_json(indent=4)}"
            )

    installed_snaps = await setup_lxd_client.snaps.list_installed_snaps()
    assert "hello-world" in [snap.name for snap in installed_snaps.result]

    # remove the snap
    await setup_lxd_client.snaps.remove_snap(
        "hello-world", purge=True, terminate=True, wait=True
    )

    installed_snaps = await setup_lxd_client.snaps.list_installed_snaps()
    assert "hello-world" not in [snap.name for snap in installed_snaps.result]
