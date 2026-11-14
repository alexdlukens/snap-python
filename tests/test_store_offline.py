import pathlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from snap_python.client import SnapClient
from snap_python.components.store import StoreEndpoints

DATA_DIR = pathlib.Path(__file__).parent / "data"
SEARCH_BODY = {"results": [{"name": "hello-world", "snap": {}, "snap-id": "abc"}]}


def make_response(
    status_code: int = 200,
    json_body: dict | None = None,
    content: bytes | None = None,
) -> httpx.Response:
    return httpx.Response(
        status_code,
        json=json_body if content is None else None,
        content=content,
        request=httpx.Request("GET", "http://store.test"),
    )


@pytest.fixture
def store() -> StoreEndpoints:
    return StoreEndpoints(base_url="http://store.test", version="v2")


@pytest.mark.asyncio
async def test_find_omits_unset_boolean_filters(store: StoreEndpoints):
    store.store_client.get = AsyncMock(return_value=make_response(200, SEARCH_BODY))

    await store.find(query="hello")

    params = store.store_client.get.await_args.kwargs["params"]
    assert params == {"q": "hello"}


@pytest.mark.asyncio
async def test_find_sends_explicit_boolean_filters(store: StoreEndpoints):
    store.store_client.get = AsyncMock(return_value=make_response(200, SEARCH_BODY))

    await store.find(featured=True, private=False)

    params = store.store_client.get.await_args.kwargs["params"]
    assert params["featured"] == "true"
    assert params["private"] == "false"


@pytest.mark.asyncio
async def test_find_forwards_confinement(store: StoreEndpoints):
    store.store_client.get = AsyncMock(return_value=make_response(200, SEARCH_BODY))

    await store.find(confinement="strict")

    params = store.store_client.get.await_args.kwargs["params"]
    assert params["confinement"] == "strict"


@pytest.mark.asyncio
async def test_get_snap_name_from_snap_id_uses_configured_base_url(
    store: StoreEndpoints,
):
    store.store_client.get = AsyncMock(
        return_value=make_response(200, {"headers": {"snap-name": "hello-world"}})
    )

    name = await store.get_snap_name_from_snap_id("snap-id-123")

    assert name == "hello-world"
    url = store.store_client.get.await_args.args[0]
    assert url == "http://store.test/v2/assertions/snap-declaration/16/snap-id-123"
    assert "api.snapcraft.io" not in url


@pytest.mark.asyncio
async def test_get_snap_info_raises_when_snap_id_unresolved(store: StoreEndpoints):
    store.store_client.get = AsyncMock(return_value=make_response(200, {"headers": {}}))

    with pytest.raises(ValueError, match="Could not resolve a snap name"):
        await store.get_snap_info(snap_id="snap-id-123")

    # only the assertion lookup was attempted, never /snaps/info/None
    assert store.store_client.get.await_count == 1
    url = store.store_client.get.await_args.args[0]
    assert "assertions/snap-declaration" in url


@pytest.mark.asyncio
async def test_get_snap_info_resolves_snap_id_to_name(store: StoreEndpoints):
    info_content = (DATA_DIR / "snap_info_response_success.json").read_bytes()

    store.store_client.get = AsyncMock(
        side_effect=[
            make_response(200, {"headers": {"snap-name": "py-rand-tool"}}),
            make_response(200, content=info_content),
        ]
    )

    response = await store.get_snap_info(snap_id="snap-id-123")

    assert response.name == "py-rand-tool"
    second_url = store.store_client.get.await_args_list[1].args[0]
    assert second_url.endswith("/v2/snaps/info/py-rand-tool")


@pytest.mark.asyncio
async def test_store_close_closes_http_client(store: StoreEndpoints):
    store.store_client.aclose = AsyncMock()
    await store.close()
    store.store_client.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_client_close_awaits_both_clients():
    client = SnapClient(version="v2")
    client.snapd_client.aclose = AsyncMock()
    client.store.store_client.aclose = AsyncMock()

    await client.close()

    client.snapd_client.aclose.assert_awaited_once()
    client.store.store_client.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_client_async_context_manager_closes():
    client = SnapClient(version="v2")
    client.snapd_client.aclose = AsyncMock()
    client.store.store_client.aclose = AsyncMock()

    async with client as entered:
        assert entered is client

    client.snapd_client.aclose.assert_awaited_once()
    client.store.store_client.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_snap_details_returns_raw_dict(store: StoreEndpoints):
    payload = {"name": "hello-world", "architecture": ["amd64"]}
    store.store_client.get = AsyncMock(return_value=make_response(200, payload))

    details = await store.get_snap_details("hello-world")

    assert details == payload


@pytest.mark.asyncio
async def test_find_sends_documented_hyphenated_wire_params(store: StoreEndpoints):
    store.store_client.get = AsyncMock(return_value=make_response(200, SEARCH_BODY))

    await store.find(
        query="hello",
        name_startswith="hello-world",
        common_id="org.kde.krita",
    )

    params = store.store_client.get.await_args.kwargs["params"]
    assert params["name-startswith"] == "hello-world"
    assert params["common-id"] == "org.kde.krita"
    assert "name_startswith" not in params
    assert "common_id" not in params


REFRESH_BODY = {
    "results": [
        {
            "name": "store-tui",
            "snap": {"name": "store-tui"},
            "instance-key": "instance-key",
            "result": "download",
            "snap-id": "store-tui-snap-id",
        }
    ]
}


async def _call_revision_info(store: StoreEndpoints, method_name: str, **kwargs):
    store.get_snap_info = AsyncMock(
        return_value=SimpleNamespace(
            snap_id="store-tui-snap-id",
            channel_map=[SimpleNamespace(revision=29)],
        )
    )
    store.snap_refresh = AsyncMock(return_value=make_response(200, REFRESH_BODY))
    if method_name == "get_snap_revision_info":
        await store.get_snap_revision_info("store-tui", 20, "amd64", **kwargs)
    else:
        await store.get_many_snap_revision_info("store-tui", 20, 22, "amd64", **kwargs)
    return store.snap_refresh.await_args.kwargs["payload"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method_name", ["get_snap_revision_info", "get_many_snap_revision_info"]
)
async def test_revision_info_omits_fields_when_none(
    store: StoreEndpoints, method_name: str
):
    payload = await _call_revision_info(store, method_name)

    assert "fields" not in payload


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method_name", ["get_snap_revision_info", "get_many_snap_revision_info"]
)
async def test_revision_info_sends_fields_when_supplied(
    store: StoreEndpoints, method_name: str
):
    payload = await _call_revision_info(store, method_name, fields=["name"])

    assert payload["fields"] == ["name"]
