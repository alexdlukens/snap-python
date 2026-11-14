import httpx
import pytest

from snap_python.client import SnapClient
from snap_python.components.snaps import SnapsEndpoints
from snap_python.schemas.changes import ChangesResponse
from snap_python.utils import AbstractSnapsClient, SnapdAPIError, wait_for_change

SPAWN_TIME = "2024-01-01T00:00:00+00:00"


def make_change(
    ready: bool = False,
    err: str | None = None,
    error_message: str | None = None,
    change_id: str = "1",
) -> ChangesResponse:
    """Build a ChangesResponse as snapd would return it."""
    if error_message is not None:
        result = {"message": error_message}
        status = "Error"
    else:
        result = {
            "id": change_id,
            "kind": "install-snap",
            "summary": "Install snap",
            "status": "Done" if ready else "Doing",
            "tasks": [],
            "ready": ready,
            "spawn-time": SPAWN_TIME,
        }
        if err is not None:
            result["err"] = err
        status = "Error" if err else result["status"]

    return ChangesResponse.model_validate(
        {
            "status-code": 200,
            "type": "async",
            "status": status,
            "result": result,
        }
    )


def async_response_payload(change_id: str = "1") -> dict:
    return {
        "status-code": 202,
        "type": "async",
        "status": "Accepted",
        "change": change_id,
    }


class ScriptedClient(AbstractSnapsClient):
    """Client stub that replays a scripted sequence of change responses."""

    def __init__(self, changes: list[ChangesResponse]):
        self._changes = changes
        self.change_calls = 0
        self.requests: list[tuple[str, str]] = []

    async def request(self, method: str, endpoint: str, **kwargs) -> httpx.Response:
        self.requests.append((method, endpoint))
        return httpx.Response(
            202,
            json=async_response_payload(),
            request=httpx.Request(method, f"http://snapd.test/v2/{endpoint}"),
        )

    async def request_raw(self, method: str, endpoint: str, **kwargs):
        return await self.request(method, endpoint, **kwargs)

    async def get_changes_by_id(self, change_id: str) -> ChangesResponse:
        self.change_calls += 1
        if not self._changes:
            raise AssertionError("no scripted change left")
        if len(self._changes) > 1:
            return self._changes.pop(0)
        return self._changes[0]


@pytest.mark.asyncio
async def test_install_snap_wait_success():
    client = ScriptedClient([make_change(), make_change(), make_change(ready=True)])
    snaps = SnapsEndpoints(client)

    response = await snaps.install_snap("hello-world", wait=True)

    assert isinstance(response, ChangesResponse)
    assert response.ready is True
    assert client.change_calls == 3
    assert client.requests == [("POST", "snaps/hello-world")]


@pytest.mark.asyncio
async def test_install_snap_wait_raises_on_error_result():
    # A failed change is also reported as ready; the error must win.
    client = ScriptedClient(
        [make_change(), make_change(ready=True, err="cannot install: conflict")]
    )
    snaps = SnapsEndpoints(client)

    with pytest.raises(SnapdAPIError, match="conflict"):
        await snaps.install_snap("hello-world", wait=True)


@pytest.mark.asyncio
async def test_install_snap_wait_raises_on_base_error_result():
    client = ScriptedClient([make_change(error_message="change not found")])
    snaps = SnapsEndpoints(client)

    with pytest.raises(SnapdAPIError, match="change not found"):
        await snaps.install_snap("hello-world", wait=True)


@pytest.mark.asyncio
async def test_install_snap_wait_timeout():
    client = ScriptedClient([make_change()])
    snaps = SnapsEndpoints(client)

    with pytest.raises(SnapdAPIError, match="Timed out"):
        await snaps.install_snap("hello-world", wait=True, timeout=0.05)


@pytest.mark.asyncio
async def test_remove_snap_wait_success():
    client = ScriptedClient([make_change(), make_change(ready=True)])
    snaps = SnapsEndpoints(client)

    response = await snaps.remove_snap("hello-world", wait=True)

    assert response.ready is True
    assert client.requests == [("POST", "snaps/hello-world")]


@pytest.mark.asyncio
async def test_remove_snap_wait_raises_on_error_result():
    client = ScriptedClient([make_change(ready=True, err="cannot remove")])
    snaps = SnapsEndpoints(client)

    with pytest.raises(SnapdAPIError, match="cannot remove"):
        await snaps.remove_snap("hello-world", wait=True)


@pytest.mark.asyncio
async def test_wait_for_change_invokes_progress_callback():
    client = ScriptedClient([make_change(), make_change(), make_change(ready=True)])
    seen: list[ChangesResponse] = []

    response = await wait_for_change(
        client, "1", poll_interval=0.01, progress_callback=seen.append
    )

    assert response.ready is True
    assert len(seen) == 3


@pytest.mark.asyncio
async def test_wait_for_change_timeout_uses_poll_interval():
    client = ScriptedClient([make_change()])

    with pytest.raises(SnapdAPIError, match="Timed out"):
        await wait_for_change(client, "1", timeout=0.05, poll_interval=0.01)


@pytest.mark.asyncio
async def test_wait_for_change_reraises_non_reload_http_error():
    class FailingClient(ScriptedClient):
        async def get_changes_by_id(self, change_id: str) -> ChangesResponse:
            response = httpx.Response(
                500,
                json={"status-code": 500, "type": "error", "status": "Internal"},
                request=httpx.Request("GET", "http://snapd.test/v2/changes/1"),
            )
            raise httpx.HTTPStatusError(
                "boom", request=response.request, response=response
            )

    with pytest.raises(httpx.HTTPStatusError):
        await wait_for_change(FailingClient([]), "1", poll_interval=0.01)


def _snapd_response(payload: dict) -> httpx.Response:
    return httpx.Response(
        200,
        json=payload,
        request=httpx.Request("GET", "http://snapd.test/v2/changes/1"),
    )


@pytest.mark.asyncio
async def test_change_generator_raises_on_error_result(monkeypatch):
    client = SnapClient(version="v2")
    payload = make_change(ready=True, err="install failed").model_dump(
        mode="json", by_alias=True
    )

    async def fake_request(method, url, **kwargs):
        return _snapd_response(payload)

    monkeypatch.setattr(client.snapd_client, "request", fake_request)

    with pytest.raises(SnapdAPIError, match="install failed"):
        async for _ in client.get_changes_by_id_generator("1"):
            pass


@pytest.mark.asyncio
async def test_change_generator_stops_at_ready(monkeypatch):
    client = SnapClient(version="v2")
    payloads = [
        make_change().model_dump(mode="json", by_alias=True),
        make_change(ready=True).model_dump(mode="json", by_alias=True),
    ]
    calls = 0

    async def fake_request(method, url, **kwargs):
        nonlocal calls
        payload = payloads[min(calls, len(payloads) - 1)]
        calls += 1
        return _snapd_response(payload)

    monkeypatch.setattr(client.snapd_client, "request", fake_request)

    seen = []
    async for change in client.get_changes_by_id_generator("1", poll_interval=0.01):
        seen.append(change)

    assert len(seen) == 2
    assert seen[-1].ready is True
    assert calls == 2


@pytest.mark.asyncio
async def test_change_generator_times_out(monkeypatch):
    client = SnapClient(version="v2")
    payload = make_change().model_dump(mode="json", by_alias=True)

    async def fake_request(method, url, **kwargs):
        return _snapd_response(payload)

    monkeypatch.setattr(client.snapd_client, "request", fake_request)

    with pytest.raises(SnapdAPIError, match="Timed out"):
        async for _ in client.get_changes_by_id_generator(
            "1", timeout=0.05, poll_interval=0.01
        ):
            pass
