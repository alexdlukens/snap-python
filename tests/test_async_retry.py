import asyncio

import httpx
import pytest

from snap_python.client import SnapClient
from snap_python.utils import async_retry, is_transient_exception


def _response(status_code: int, payload: dict | None = None) -> httpx.Response:
    return httpx.Response(
        status_code,
        json=payload or {},
        request=httpx.Request("GET", "http://snapd.test/v2/changes/1"),
    )


@pytest.mark.asyncio
async def test_async_retry_retries_until_success(monkeypatch):
    sleeps: list[float] = []

    async def fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    calls = 0

    @async_retry(httpx.HTTPError, tries=3, delay=0.5, backoff=2)
    async def flaky():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise httpx.ConnectError("boom")
        return "ok"

    assert await flaky() == "ok"
    assert calls == 3
    # delays are awaited through asyncio.sleep, with exponential backoff
    assert sleeps == [0.5, 1.0]


@pytest.mark.asyncio
async def test_async_retry_does_not_retry_4xx(monkeypatch):
    sleeps: list[float] = []

    async def fake_sleep(delay):  # pragma: no cover - must not be called
        sleeps.append(delay)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    calls = 0

    @async_retry(httpx.HTTPError, tries=3, delay=0.5)
    async def not_found():
        nonlocal calls
        calls += 1
        response = _response(404, {"status": "Not Found"})
        raise httpx.HTTPStatusError(
            "Not Found", request=response.request, response=response
        )

    with pytest.raises(httpx.HTTPStatusError):
        await not_found()
    assert calls == 1
    assert sleeps == []


@pytest.mark.asyncio
async def test_async_retry_exhausts_tries(monkeypatch):
    async def fake_sleep(delay):
        return None

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    calls = 0

    @async_retry(httpx.HTTPError, tries=3, delay=0)
    async def always_down():
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("boom")

    with pytest.raises(httpx.ConnectError):
        await always_down()
    assert calls == 3


def test_is_transient_exception():
    transient = httpx.ConnectError("boom")
    assert is_transient_exception(transient) is True
    assert is_transient_exception(httpx.ReadTimeout("slow")) is True

    def status_error(code: int) -> httpx.HTTPStatusError:
        response = _response(code)
        return httpx.HTTPStatusError(
            "error", request=response.request, response=response
        )

    assert is_transient_exception(status_error(429)) is True
    assert is_transient_exception(status_error(500)) is True
    assert is_transient_exception(status_error(503)) is True
    assert is_transient_exception(status_error(400)) is False
    assert is_transient_exception(status_error(404)) is False


@pytest.mark.asyncio
async def test_request_retries_transient_get_errors(monkeypatch):
    sleeps: list[float] = []

    async def fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    client = SnapClient(version="v2")
    calls = 0

    async def fake_request(method, url, **kwargs):
        nonlocal calls
        calls += 1
        if calls < 2:
            raise httpx.ConnectError("boom")
        return _response(200, {"status": "OK", "type": "sync", "status-code": 200})

    monkeypatch.setattr(client.snapd_client, "request", fake_request)

    response = await client.request("GET", "system-info")
    assert response.status_code == 200
    assert calls == 2


@pytest.mark.asyncio
async def test_request_does_not_retry_post(monkeypatch):
    sleeps: list[float] = []

    async def fake_sleep(delay):  # pragma: no cover - must not be called
        sleeps.append(delay)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    client = SnapClient(version="v2")
    calls = 0

    async def fake_request(method, url, **kwargs):
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(client.snapd_client, "request", fake_request)

    with pytest.raises(httpx.ConnectError):
        await client.request("POST", "snaps/hello-world", json={})
    assert calls == 1
    assert sleeps == []


@pytest.mark.asyncio
async def test_get_changes_by_id_raises_on_http_error(monkeypatch):
    client = SnapClient(version="v2")
    calls = 0

    async def fake_request(method, url, **kwargs):
        nonlocal calls
        calls += 1
        return _response(404, {"status-code": 404, "type": "error"})

    monkeypatch.setattr(client.snapd_client, "request", fake_request)

    with pytest.raises(httpx.HTTPStatusError):
        await client.get_changes_by_id("unknown-change-id")
    assert calls == 1


@pytest.mark.asyncio
async def test_ping_raises_on_error_status(monkeypatch):
    client = SnapClient(version="v2")
    monkeypatch.setattr(
        client.snapd_client, "get", AsyncMockReturning(_response(200, {"ok": True}))
    )
    response = await client.ping()
    assert response.status_code == 200

    monkeypatch.setattr(
        client.snapd_client, "get", AsyncMockReturning(_response(500, {"err": True}))
    )
    with pytest.raises(httpx.HTTPStatusError):
        await client.ping()


@pytest.mark.asyncio
async def test_is_available(monkeypatch):
    client = SnapClient(version="v2")
    monkeypatch.setattr(
        client.snapd_client, "get", AsyncMockReturning(_response(200, {"ok": True}))
    )
    assert await client.is_available() is True

    monkeypatch.setattr(
        client.snapd_client, "get", AsyncMockReturning(_response(503, {"err": True}))
    )
    assert await client.is_available() is False


@pytest.mark.asyncio
async def test_is_available_on_transport_error(monkeypatch):
    client = SnapClient(version="v2")

    async def raise_connect(*args, **kwargs):
        raise httpx.ConnectError("no socket")

    monkeypatch.setattr(client.snapd_client, "get", raise_connect)
    assert await client.is_available() is False


class AsyncMockReturning:
    """Minimal async callable returning a preset value."""

    def __init__(self, value):
        self.value = value

    async def __call__(self, *args, **kwargs):
        return self.value
