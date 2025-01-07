import asyncio
import logging
from pathlib import Path

import httpx
import pytest

from snap_python.client import SnapClient
from snap_python.schemas.changes import ChangesResponse
from snap_python.schemas.common import AsyncResponse, BaseErrorResult

BASE_DIR = Path(__file__).resolve().parent.parent
CODE_DIR = BASE_DIR / "src" / "snap_python"
TEST_DIR = BASE_DIR / "tests"
TEST_DATA_DIR = TEST_DIR / "data"

logger = logging.getLogger("snap_python.tests.test_snap_python_snaps_endpoints")
logger.setLevel(logging.DEBUG)
logger.handlers.clear()
logger.propagate = True


@pytest.mark.asyncio
async def test_snap_client_list_snaps(module_scope_client: SnapClient):
    logger.debug("Running test_snap_client_list_snaps")
    installed_snaps = []
    try:
        installed_snaps = await module_scope_client.snaps.list_installed_snaps()
    except httpx.HTTPStatusError as e:
        pytest.fail(
            f"List installed snaps failed with status code {e.response.status_code}"
        )
    assert len(installed_snaps) == 0


@pytest.mark.asyncio
async def test_snap_client_install_snap_no_wait(module_scope_client: SnapClient):
    logger.debug("Running test_snap_client_install_snap")
    response = await module_scope_client.snaps.install_snap("hello-world")
    assert response.status_code == 202

    while True:
        changes = await module_scope_client.get_changes_by_id(response.change)
        assert changes.status_code == 200
        if changes.result.ready:
            logger.debug("Snap hello-world installed successfully")
            break
        await asyncio.sleep(1.0)

    installed_snaps = await module_scope_client.snaps.list_installed_snaps()
    snap_names = [snap.name for snap in installed_snaps.result]
    assert "hello-world" in snap_names
    assert "core" in snap_names

    logger.debug("Removing the snap now")
    # remove the snap
    removal_response = await module_scope_client.snaps.remove_snap(
        "hello-world", purge=True, terminate=True
    )
    assert removal_response.status_code == 202

    while True:
        changes = await module_scope_client.get_changes_by_id(removal_response.change)
        if changes.result.ready:
            logger.debug("Snap hello-world removed successfully")
            break
        await asyncio.sleep(1.0)

    installed_snaps = await module_scope_client.snaps.list_installed_snaps()
    assert "hello-world" not in [snap.name for snap in installed_snaps.result]


@pytest.mark.asyncio
async def test_snap_client_install_with_wait(module_scope_client: SnapClient):
    logger.debug("Running test_snap_client_install_with_wait")
    response = await module_scope_client.snaps.install_snap("hello-world", wait=True)
    assert isinstance(response, ChangesResponse)
    assert response.status_code == 200
    assert await module_scope_client.snaps.is_snap_installed("hello-world") is True
    installed_snaps = await module_scope_client.snaps.list_installed_snaps()
    assert "hello-world" in [snap.name for snap in installed_snaps.result]

    logger.debug("Removing the snap now")

    removal_response = await module_scope_client.snaps.remove_snap(
        "hello-world", purge=True, terminate=True, wait=True
    )
    assert removal_response.status_code == 200

    installed_snaps = await module_scope_client.snaps.list_installed_snaps()
    assert "hello-world" not in [snap.name for snap in installed_snaps.result]
    assert await module_scope_client.snaps.is_snap_installed("hello-world") is False


@pytest.mark.asyncio
async def test_get_unknown_change(module_scope_client: SnapClient):
    logger.debug("Running test_get_unknown_change")

    bad_response = await module_scope_client.get_changes_by_id("unknown-change-id")

    assert bad_response.status_code == 404
    assert bad_response.status == "Not Found"
    assert isinstance(bad_response.result, BaseErrorResult)
    assert bad_response.type == "error"


@pytest.mark.asyncio
async def test_install_specific_snap_revision_channel(module_scope_client: SnapClient):
    logger.debug("Running test_install_specific_snap_revision_channel")
    response = await module_scope_client.snaps.install_snap(
        "usconstitution", channel="latest/edge", revision=96, wait=True
    )
    assert isinstance(response, ChangesResponse)
    assert response.status_code == 200

    installed_snaps = await module_scope_client.snaps.list_installed_snaps()
    assert "usconstitution" in [snap.name for snap in installed_snaps.result]

    constitution_snap = [
        snap for snap in installed_snaps.result if snap.name == "usconstitution"
    ][0]
    assert constitution_snap.revision == "96"
    assert constitution_snap.channel == "latest/edge"

    removal_response = await module_scope_client.snaps.remove_snap(
        "usconstitution", purge=True, terminate=True, wait=True
    )
    assert removal_response.status_code == 200

    installed_snaps = await module_scope_client.snaps.list_installed_snaps()
    assert "usconstitution" not in [snap.name for snap in installed_snaps.result]


@pytest.mark.asyncio
async def test_get_snap_info(module_scope_client: SnapClient):
    logger.debug("Running test_get_snap_info")

    # install hello-world snap
    response = await module_scope_client.snaps.install_snap("hello-world", wait=True)

    # ensure snap shows up in list_installed_snaps
    installed_snaps = await module_scope_client.snaps.list_installed_snaps()
    assert "hello-world" in [snap.name for snap in installed_snaps.result]

    # ensure snap info can be retrieved using get_snap_info
    snap_info = await module_scope_client.snaps.get_snap_info("hello-world")
    assert snap_info.status_code == 200

    # ensure snap info is identical to item in list_installed_snaps
    snap_info = snap_info.result
    snap = [snap for snap in installed_snaps.result if snap.name == "hello-world"][0]

    # remove snap
    removal_response = await module_scope_client.snaps.remove_snap(
        "hello-world", purge=True, terminate=True, wait=True
    )

    assert snap_info == snap


@pytest.mark.asyncio
async def test_install_snap_async_generator(module_scope_client: SnapClient):
    logger.debug("Running test_install_snap_async_generator")

    async_install_response: AsyncResponse = (
        await module_scope_client.snaps.install_snap("hello-world", wait=False)
    )

    count = 0
    async for change in module_scope_client.get_changes_by_id_generator(
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

    installed_snaps = await module_scope_client.snaps.list_installed_snaps()
    assert "hello-world" in [snap.name for snap in installed_snaps.result]

    # remove the snap
    await module_scope_client.snaps.remove_snap(
        "hello-world", purge=True, terminate=True, wait=True
    )

    installed_snaps = await module_scope_client.snaps.list_installed_snaps()
    assert "hello-world" not in [snap.name for snap in installed_snaps.result]


@pytest.mark.asyncio
async def install_snap_edgecase_health(module_scope_client: SnapClient):
    logger.debug("Running test_install_snap_edgecase_health")
    microk8s_snap_name = "microk8s"

    response = await module_scope_client.snaps.install_snap(
        microk8s_snap_name, wait=True
    )

    # ensure snap shows up in list_installed_snaps
    installed_snaps = await module_scope_client.snaps.list_installed_snaps()
    assert microk8s_snap_name in [snap.name for snap in installed_snaps.result]

    # ensure snap info can be retrieved using get_snap_info
    snap_info = await module_scope_client.snaps.get_snap_info(microk8s_snap_name)
    assert snap_info.status_code == 200

    # ensure snap info has health information (this is the only snap I have
    # seen that has the health key)
    assert snap_info.result.health is not None

    # remove snap
    removal_response = await module_scope_client.snaps.remove_snap(
        microk8s_snap_name, purge=True, terminate=True, wait=True
    )
