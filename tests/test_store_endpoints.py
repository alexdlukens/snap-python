import pathlib
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import HTTPError, Response

from snap_python.client import StoreEndpoints
from snap_python.schemas.store.categories import (
    CategoryResponse,
)
from snap_python.schemas.store.info import InfoResponse


@pytest.fixture(scope="function")
def setup_snaps_api():
    return StoreEndpoints(base_url="http://localhost:8000", version="v1")


@pytest.mark.asyncio
async def test_get_categories_success(setup_snaps_api: StoreEndpoints):
    setup_snaps_api.store_client.get = AsyncMock()
    setup_snaps_api.store_client.get.return_value.status_code = 200
    setup_snaps_api.store_client.get.return_value.content = b'{"categories":[{"name":"art-and-design"},{"name":"books-and-reference"},{"name":"development"},{"name":"devices-and-iot"},{"name":"education"},{"name":"entertainment"},{"name":"featured"},{"name":"finance"},{"name":"games"},{"name":"health-and-fitness"},{"name":"music-and-audio"},{"name":"news-and-weather"},{"name":"personalisation"},{"name":"photo-and-video"},{"name":"productivity"},{"name":"science"},{"name":"security"},{"name":"server-and-cloud"},{"name":"social"},{"name":"utilities"}]}\n'
    setup_snaps_api.store_client.get.return_value.raise_for_status = MagicMock()
    response = await setup_snaps_api.get_categories()
    assert isinstance(response, CategoryResponse)
    assert response.categories is not None
    assert len(response.categories) == 20


@pytest.mark.asyncio
async def test_get_categories_fail_bad_field(setup_snaps_api: StoreEndpoints):
    setup_snaps_api.store_client.get = AsyncMock()
    setup_snaps_api.store_client.get.return_value.status_code = 200
    setup_snaps_api.store_client.get.return_value.content = b'{"categories":[{"name":"art-and-design"},{"name":"books-and-reference"},{"name":"development"},{"name":"devices-and-iot"},{"name":"education"},{"name":"entertainment"},{"name":"featured"},{"name":"finance"},{"name":"games"},{"name":"health-and-fitness"},{"name":"music-and-audio"},{"name":"news-and-weather"},{"name":"personalisation"},{"name":"photo-and-video"},{"name":"productivity"},{"name":"science"},{"name":"security"},{"name":"server-and-cloud"},{"name":"social"},{"name":"utilities"}]}\n'
    try:
        await setup_snaps_api.get_categories(fields=["bad-category"])
        pytest.fail("Expected ValueError")
    except ValueError:
        pass


@pytest.mark.asyncio
async def test_get_categories_fail_500(setup_snaps_api: StoreEndpoints):
    setup_snaps_api.store_client.get = AsyncMock()
    setup_snaps_api.store_client.get.return_value = Response(
        status_code=500, request=MagicMock()
    )

    try:
        await setup_snaps_api.get_categories()
        pytest.fail("Expected HTTPError")
    except HTTPError:
        pass


@pytest.mark.asyncio
async def test_get_snap_info_success(setup_snaps_api: StoreEndpoints):
    SNAP_INFO_RESPONSE_SUCCESS_DATA_FILE = (
        pathlib.Path(__file__).parent / "data" / "snap_info_response_success.json"
    )

    setup_snaps_api.store_client.get = AsyncMock()
    setup_snaps_api.store_client.get.return_value.status_code = 200
    with open(SNAP_INFO_RESPONSE_SUCCESS_DATA_FILE, "rb") as f:
        setup_snaps_api.store_client.get.return_value.content = f.read()
    setup_snaps_api.store_client.get.return_value.raise_for_status = MagicMock()
    try:
        response = await setup_snaps_api.get_snap_info("py-rand-tool")
    except Exception as e:
        pytest.fail(f"Unexpected exception: {e}")
    assert isinstance(response, InfoResponse)
