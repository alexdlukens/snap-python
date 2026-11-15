import json

import httpx
import pytest

from snap_python.client import SnapClient
from snap_python.schemas.changes import ChangesResponse
from snap_python.schemas.common import AsyncResponse
from snap_python.schemas.interfaces import (
    ConnectionsResponse,
    InterfacesResponse,
    PlugRef,
    SlotRef,
)
from snap_python.utils import SnapdAPIError

SPAWN_TIME = "2024-01-01T00:00:00Z"

MODERN_INTERFACES = [
    {
        "name": "network",
        "summary": "Network access",
        "doc-url": "https://snapcraft.io/docs/network-interface",
        "plugs": [
            {
                "snap": "hello",
                "plug": "network",
                "attrs": {"bind": ["tcp"]},
                "label": "net",
            }
        ],
        "slots": [{"snap": "core", "slot": "network"}],
    },
    {"name": "home", "summary": "Home access", "doc-url": "https://example.test/home"},
]

LEGACY_INTERFACES = {
    "plugs": [
        {
            "snap": "hello",
            "plug": "home",
            "interface": "home",
            "attrs": {"read": ["$HOME"]},
            "apps": ["hello"],
            "label": "home",
            "connections": [{"snap": "core", "slot": "home"}],
        }
    ],
    "slots": [
        {
            "snap": "core",
            "slot": "home",
            "interface": "home",
            "connections": [{"snap": "hello", "plug": "home"}],
        }
    ],
}

CONNECTIONS = {
    "established": [
        {
            "slot": {"snap": "core", "slot": "network"},
            "plug": {"snap": "hello", "plug": "network"},
            "interface": "network",
            "manual": True,
            "slot-attrs": {"bind": ["tcp"]},
        }
    ],
    "plugs": [
        {
            "snap": "hello",
            "plug": "network",
            "interface": "network",
            "attrs": {"bind": ["tcp"]},
            "apps": ["hello"],
            "connections": [{"snap": "core", "slot": "network"}],
        }
    ],
    "slots": [
        {
            "snap": "core",
            "slot": "network",
            "interface": "network",
            "connections": [{"snap": "hello", "plug": "network"}],
        }
    ],
}

ASYNC_ACCEPTED = {
    "status-code": 202,
    "type": "async",
    "status": "Accepted",
    "result": None,
    "change": "1",
}


def make_client(handler) -> SnapClient:
    """Build a SnapClient whose snapd transport is a MockTransport."""
    client = SnapClient(version="v2")
    client.snapd_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client


def envelope(result, status_code: int = 200, status: str = "OK") -> dict:
    return {
        "status-code": status_code,
        "type": "sync",
        "status": status,
        "result": result,
    }


def change_envelope(ready: bool = True) -> dict:
    return envelope(
        {
            "id": "1",
            "kind": "connect-snap",
            "summary": "Connect hello:network to core:network",
            "status": "Done" if ready else "Doing",
            "ready": ready,
            "spawn-time": SPAWN_TIME,
        }
    )


# --- GET /v2/interfaces --------------------------------------------------


@pytest.mark.asyncio
async def test_list_interfaces_serialises_flags_and_names():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json=envelope(MODERN_INTERFACES))

    client = make_client(handler)

    response = await client.interfaces.list_interfaces(
        select="all", plugs=True, slots=True, doc=True, names=["network", "home"]
    )

    request = captured["request"]
    assert request.url.path == "/v2/interfaces"
    params = request.url.params
    assert params["select"] == "all"
    assert params["plugs"] == "true"
    assert params["slots"] == "true"
    assert params["doc"] == "true"
    assert params["names"] == "network,home"

    assert isinstance(response, InterfacesResponse)
    assert response.legacy is False
    assert [interface.name for interface in response.interfaces] == ["network", "home"]
    assert (
        response.interfaces[0].doc_url == "https://snapcraft.io/docs/network-interface"
    )
    assert response.interfaces[0].plugs == [PlugRef(snap="hello", plug="network")]
    assert response.interfaces[0].slots == [SlotRef(snap="core", slot="network")]


@pytest.mark.asyncio
async def test_list_interfaces_without_select_parses_legacy_shape():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json=envelope(LEGACY_INTERFACES))

    client = make_client(handler)

    response = await client.interfaces.list_interfaces()

    # No select parameter at all is what selects the legacy handler.
    assert "select" not in captured["request"].url.params
    assert response.legacy is True

    # Raw models keep the fields the modern shape never carries.
    assert response.result.plugs[0].apps == ["hello"]
    assert response.result.plugs[0].attrs == {"read": ["$HOME"]}
    assert response.result.plugs[0].connections == [SlotRef(snap="core", slot="home")]
    assert response.result.slots[0].connections == [PlugRef(snap="hello", plug="home")]

    assert [interface.name for interface in response.interfaces] == ["home"]
    assert response.interfaces[0].plugs == [PlugRef(snap="hello", plug="home")]
    assert response.interfaces[0].slots == [SlotRef(snap="core", slot="home")]


@pytest.mark.asyncio
async def test_list_interfaces_modern_flags_not_requested_are_empty():
    payload = [{"name": "network", "summary": "Network access"}]

    client = make_client(lambda request: httpx.Response(200, json=envelope(payload)))

    response = await client.interfaces.list_interfaces(select="connected")

    assert response.interfaces[0].plugs == []
    assert response.interfaces[0].slots == []
    assert response.interfaces[0].doc_url is None


# --- GET /v2/connections -------------------------------------------------


@pytest.mark.asyncio
async def test_connections_serialises_filters_and_parses_result():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json=envelope(CONNECTIONS))

    client = make_client(handler)

    response = await client.interfaces.connections(
        snap="hello", select="all", interface="network"
    )

    request = captured["request"]
    assert request.url.path == "/v2/connections"
    params = request.url.params
    assert params["snap"] == "hello"
    assert params["select"] == "all"
    assert params["interface"] == "network"

    assert isinstance(response, ConnectionsResponse)
    connections = response.connections
    assert connections.established[0].plug == PlugRef(snap="hello", plug="network")
    assert connections.established[0].slot == SlotRef(snap="core", slot="network")
    assert connections.established[0].manual is True
    # gadget and undesired are omitempty on the wire.
    assert connections.established[0].gadget is False
    assert connections.undesired is None
    assert connections.established[0].slot_attrs == {"bind": ["tcp"]}
    assert connections.established[0].plug_attrs is None
    assert connections.plugs[0].apps == ["hello"]
    assert connections.slots[0].connections == [PlugRef(snap="hello", plug="network")]


@pytest.mark.asyncio
async def test_connections_omits_filters_by_default():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(
            200, json=envelope({"established": [], "plugs": [], "slots": []})
        )

    client = make_client(handler)

    response = await client.interfaces.connections()

    assert captured["request"].url.params == httpx.QueryParams()
    assert response.connections.established == []
    assert response.connections.plugs == []


@pytest.mark.asyncio
async def test_connections_unknown_snap_surfaces_snap_not_found():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={
                "status-code": 404,
                "type": "error",
                "status": "Not Found",
                "result": {
                    "message": "no state entry for key",
                    "kind": "snap-not-found",
                    "value": "nosuch",
                },
            },
        )

    client = make_client(handler)

    with pytest.raises(SnapdAPIError) as excinfo:
        await client.interfaces.connections(snap="nosuch")

    assert excinfo.value.status_code == 404
    assert excinfo.value.kind == "snap-not-found"
    assert excinfo.value.value == "nosuch"


# --- POST /v2/interfaces -------------------------------------------------


@pytest.mark.asyncio
async def test_connect_posts_single_plug_and_slot():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(202, json=ASYNC_ACCEPTED)

    client = make_client(handler)

    response = await client.interfaces.connect(
        "hello", "network", "core", "network", wait=False
    )

    request = captured["request"]
    assert request.method == "POST"
    assert request.url.path == "/v2/interfaces"
    assert request.url.params == httpx.QueryParams()
    body = json.loads(request.content)
    assert body == {
        "action": "connect",
        "plugs": [{"snap": "hello", "plug": "network"}],
        "slots": [{"snap": "core", "slot": "network"}],
    }
    assert isinstance(response, AsyncResponse)
    assert response.change == "1"


@pytest.mark.asyncio
async def test_connect_leaves_slot_for_snapd_to_resolve():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(202, json=ASYNC_ACCEPTED)

    client = make_client(handler)

    await client.interfaces.connect("hello", "network", wait=False)

    body = json.loads(captured["request"].content)
    # Both arrays must be non-empty, so the pair is sent with empty names and
    # snapd picks the slot snap (snapd/core/ubuntu-core) and name.
    assert body["slots"] == [{"snap": "", "slot": ""}]


@pytest.mark.asyncio
async def test_disconnect_with_forget_sends_forget():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(202, json=ASYNC_ACCEPTED)

    client = make_client(handler)

    await client.interfaces.disconnect(
        "hello", "home", "core", "home", forget=True, wait=False
    )

    body = json.loads(captured["request"].content)
    assert body["action"] == "disconnect"
    assert body["forget"] is True
    assert body["plugs"] == [{"snap": "hello", "plug": "home"}]
    assert body["slots"] == [{"snap": "core", "slot": "home"}]


@pytest.mark.asyncio
async def test_disconnect_without_forget_omits_key():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(202, json=ASYNC_ACCEPTED)

    client = make_client(handler)

    await client.interfaces.disconnect("hello", "home", wait=False)

    assert "forget" not in json.loads(captured["request"].content)


@pytest.mark.asyncio
async def test_connect_body_has_no_forget_key():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(202, json=ASYNC_ACCEPTED)

    client = make_client(handler)

    await client.interfaces.connect("hello", "network", wait=False)

    assert "forget" not in json.loads(captured["request"].content)


@pytest.mark.asyncio
async def test_connect_waits_for_change():
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.method == "POST":
            return httpx.Response(202, json=ASYNC_ACCEPTED)
        return httpx.Response(200, json=change_envelope())

    client = make_client(handler)

    response = await client.interfaces.connect(
        "hello", "network", "core", "network", poll_interval=0.001
    )

    assert paths == ["/v2/interfaces", "/v2/changes/1"]
    assert isinstance(response, ChangesResponse)
    assert response.ready is True
