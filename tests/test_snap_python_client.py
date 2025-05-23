import httpx
import pytest

from snap_python.client import SnapClient


@pytest.fixture
def setup_client():
    return SnapClient(version="v2")


@pytest.mark.asyncio
async def test_snap_client_ping_200(setup_client: SnapClient):
    try:
        await setup_client.ping()
    except httpx.HTTPStatusError as e:
        pytest.fail(f"Ping failed with status code {e.response.status_code}")
