import json

import httpx
import pytest

from snap_python.client import SnapClient
from snap_python.schemas.logs import LogEntry
from snap_python.utils import SnapdAPIError

TIMESTAMP = "2025-09-11T15:10:22.264675Z"

LOG_ONE = {
    "timestamp": TIMESTAMP,
    "message": "started daemon",
    "sid": "snapd",
    "pid": "1234",
}
LOG_TWO = {
    "timestamp": "2025-09-11T15:10:23.000001Z",
    "message": "hello from an app",
    "sid": "hello.hello",
    "pid": "4321",
}


def make_client(handler) -> SnapClient:
    """Build a SnapClient whose snapd transport is a MockTransport."""
    client = SnapClient(version="v2")
    client.snapd_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client


def json_seq(*records) -> bytes:
    """Build an RFC 7464 body: each record is RS + JSON + LF.

    A ``str`` record is written verbatim so tests can embed broken records.
    """
    parts = []
    for record in records:
        payload = record if isinstance(record, str) else json.dumps(record)
        parts.append(f"\x1e{payload}\n".encode())
    return b"".join(parts)


@pytest.mark.asyncio
async def test_get_logs_serialises_names_and_n():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, content=json_seq(LOG_ONE, LOG_TWO))

    client = make_client(handler)

    entries = await client.logs.get_logs(names=["snapd", "hello.hello"], n=5)

    request = captured["request"]
    assert request.url.path == "/v2/logs"
    params = request.url.params
    assert params["names"] == "snapd,hello.hello"
    assert params["n"] == "5"
    # Buffered reads never follow; snapd defaults follow to false.
    assert "follow" not in params

    assert [entry.message for entry in entries] == [
        "started daemon",
        "hello from an app",
    ]
    assert isinstance(entries[0], LogEntry)
    assert entries[0].timestamp == TIMESTAMP
    assert entries[0].sid == "snapd"
    # snapd encodes pid as a string.
    assert entries[0].pid == "1234"


@pytest.mark.asyncio
async def test_get_logs_omits_optional_params():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, content=json_seq(LOG_ONE))

    client = make_client(handler)

    await client.logs.get_logs()

    # snapd then applies its own defaults: every service, n=10.
    assert not captured["request"].url.params


@pytest.mark.asyncio
async def test_get_logs_parses_all_entries():
    client = make_client(
        lambda request: httpx.Response(200, content=json_seq(LOG_ONE, LOG_TWO))
    )

    entries = await client.logs.get_logs()

    assert [entry.sid for entry in entries] == ["snapd", "hello.hello"]


@pytest.mark.asyncio
async def test_get_logs_skips_malformed_records():
    body = json_seq(
        LOG_ONE,
        "{not json",
        # The mid-stream reader failure record is not JSON-seq: the daemon
        # writes a literal backslash-x-1-E, not the RS byte.
        '\\x1E{"error": "cannot stream response"}',
        "unprefixed garbage",
        "",
        LOG_TWO,
    )

    client = make_client(lambda request: httpx.Response(200, content=body))

    entries = await client.logs.get_logs()

    assert [entry.message for entry in entries] == [
        "started daemon",
        "hello from an app",
    ]


@pytest.mark.asyncio
async def test_get_logs_empty_body_returns_no_entries():
    client = make_client(lambda request: httpx.Response(200, content=b""))

    assert await client.logs.get_logs() == []


@pytest.mark.asyncio
async def test_get_logs_surfaces_snapd_error_envelope():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={
                "status-code": 404,
                "type": "error",
                "status": "Not Found",
                "result": {
                    "message": 'snap "nosuch" not found',
                    "kind": "snap-not-found",
                    "value": "nosuch",
                },
            },
        )

    client = make_client(handler)

    with pytest.raises(SnapdAPIError) as excinfo:
        await client.logs.get_logs(names=["nosuch"])

    assert excinfo.value.status_code == 404
    assert excinfo.value.kind == "snap-not-found"
    assert excinfo.value.value == "nosuch"


@pytest.mark.asyncio
async def test_stream_logs_requests_follow_and_yields_entries():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        body = json_seq(LOG_ONE, "{broken", LOG_TWO)
        return httpx.Response(200, content=body)

    client = make_client(handler)

    entries = [entry async for entry in client.logs.stream_logs(names=["snapd"], n=2)]

    params = captured["request"].url.params
    assert captured["request"].url.path == "/v2/logs"
    assert params["follow"] == "true"
    assert params["names"] == "snapd"
    assert params["n"] == "2"
    assert [entry.message for entry in entries] == [
        "started daemon",
        "hello from an app",
    ]


@pytest.mark.asyncio
async def test_stream_logs_empty_body_yields_nothing():
    client = make_client(lambda request: httpx.Response(200, content=b""))

    assert [entry async for entry in client.logs.stream_logs()] == []


@pytest.mark.asyncio
async def test_stream_logs_surfaces_snapd_error_envelope():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={
                "status-code": 404,
                "type": "error",
                "status": "Not Found",
                "result": {
                    "message": "no matching services",
                    "kind": "app-not-found",
                },
            },
        )

    client = make_client(handler)

    with pytest.raises(SnapdAPIError) as excinfo:
        async for _ in client.logs.stream_logs():
            pass

    assert excinfo.value.status_code == 404
    assert excinfo.value.kind == "app-not-found"
