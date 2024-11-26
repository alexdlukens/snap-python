from pathlib import Path

import httpx
import pytest

from pysnap.client import SnapClient

BASE_DIR = Path(__file__).resolve().parent.parent
CODE_DIR = BASE_DIR / "src" / "pysnap"
TEST_DIR = BASE_DIR / "tests"
TEST_DATA_DIR = TEST_DIR / "data"


@pytest.fixture
def setup_client():
    return SnapClient(version="v2")


@pytest.fixture
def setup_lxd_client():
    return SnapClient(version="v2", snapd_socket_location="/tmp/snapd.socket")


@pytest.mark.asyncio
async def test_snap_client_list_snaps(setup_client: SnapClient):
    installed_snaps = []
    try:
        installed_snaps = await setup_client.snaps.list_installed_snaps()
    except httpx.HTTPStatusError as e:
        pytest.fail(
            f"List installed snaps failed with status code {e.response.status_code}"
        )
    assert len(installed_snaps) > 0

    with open(TEST_DATA_DIR / "installed_snaps.json", "w") as f:
        f.write(installed_snaps.model_dump_json())
