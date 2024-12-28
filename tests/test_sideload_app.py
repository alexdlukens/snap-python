import logging
from pathlib import Path

import pytest
from pylxd.models import Container

from snap_python.client import SnapClient
from tests.lib.setup_lxd_container import module_scope_container  # noqa: F401

BASE_DIR = Path(__file__).resolve().parent.parent
CODE_DIR = BASE_DIR / "src" / "snap_python"
TEST_DIR = BASE_DIR / "tests"
TEST_DATA_DIR = TEST_DIR / "data"

logger = logging.getLogger("snap_python.tests.test_sideload_app")
logger.setLevel(logging.DEBUG)
logger.handlers.clear()
logger.propagate = True

STORE_TUI_SNAP_FILE = Path(TEST_DATA_DIR / "store-tui_sideload.snap")


@pytest.fixture
def setup_lxd_client(module_scope_container: Container) -> SnapClient:
    container = module_scope_container
    logger.info(f"Container ID: {container.name}")
    return SnapClient(version="v2", tcp_location="http://127.0.0.1:8181")


async def test_sideload_store_tui(setup_lxd_client: SnapClient):
    logger.debug("Running test_sideload_store_tui")

    # list snaps
    snaps = await setup_lxd_client.snaps.list_installed_snaps()
    assert "store-tui" not in [snap.name for snap in snaps.result]

    sideload_response = await setup_lxd_client.snaps.install_snap(
        "store-tui", filename=STORE_TUI_SNAP_FILE, wait=True, dangerous=True
    )

    assert sideload_response.status_code == 200

    snaps = await setup_lxd_client.snaps.list_installed_snaps()
    assert "store-tui" in [snap.name for snap in snaps.result]

    await setup_lxd_client.snaps.remove_snap("store-tui", wait=True)

    snaps = await setup_lxd_client.snaps.list_installed_snaps()
    assert "store-tui" not in [snap.name for snap in snaps.result]
