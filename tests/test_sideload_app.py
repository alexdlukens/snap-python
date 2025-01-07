import logging
from pathlib import Path

from snap_python.client import SnapClient

BASE_DIR = Path(__file__).resolve().parent.parent
CODE_DIR = BASE_DIR / "src" / "snap_python"
TEST_DIR = BASE_DIR / "tests"
TEST_DATA_DIR = TEST_DIR / "data"

logger = logging.getLogger("snap_python.tests.test_sideload_app")
logger.setLevel(logging.DEBUG)
logger.handlers.clear()
logger.propagate = True

STORE_TUI_SNAP_FILE = Path(TEST_DATA_DIR / "store-tui_sideload.snap")


async def test_sideload_store_tui(module_scope_client: SnapClient):
    logger.debug("Running test_sideload_store_tui")

    # list snaps
    snaps = await module_scope_client.snaps.list_installed_snaps()
    assert "store-tui" not in [snap.name for snap in snaps.result]

    sideload_response = await module_scope_client.snaps.install_snap(
        "store-tui", filename=STORE_TUI_SNAP_FILE, wait=True, dangerous=True
    )

    assert sideload_response.status_code == 200

    snaps = await module_scope_client.snaps.list_installed_snaps()
    assert "store-tui" in [snap.name for snap in snaps.result]

    await module_scope_client.snaps.remove_snap("store-tui", wait=True)

    snaps = await module_scope_client.snaps.list_installed_snaps()
    assert "store-tui" not in [snap.name for snap in snaps.result]
