import json

import httpx
import pytest

from snap_python.client import SnapClient
from snap_python.schemas.changes import ChangesListResponse, ChangesResponse
from snap_python.utils import SnapdAPIError

SPAWN_TIME = "2024-01-01T00:00:00Z"


def make_client(handler) -> SnapClient:
    """Build a SnapClient whose snapd transport is a MockTransport."""
    client = SnapClient(version="v2")
    client.snapd_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client


def change_payload(
    change_id: str = "1", ready: bool = False, status: str | None = None, **extra
) -> dict:
    payload = {
        "id": change_id,
        "kind": "install-snap",
        "summary": "Install snap",
        "status": status or ("Done" if ready else "Doing"),
        "tasks": [],
        "ready": ready,
        "spawn-time": SPAWN_TIME,
    }
    payload.update(extra)
    return payload


def envelope(result, status_code: int = 200, type_: str = "sync", status: str = "OK"):
    return {
        "status-code": status_code,
        "type": type_,
        "status": status,
        "result": result,
    }


def error_payload(message: str, kind: str | None = None) -> dict:
    result = {"message": message}
    if kind is not None:
        result["kind"] = kind
    return result


@pytest.mark.asyncio
async def test_list_changes_omits_filters_by_default():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json=envelope([change_payload()]))

    client = make_client(handler)

    response = await client.changes.list_changes()

    request = captured["request"]
    assert request.method == "GET"
    assert request.url.path == "/v2/changes"
    # snapd defaults select to "in-progress"; no filter is sent.
    assert "select" not in request.url.params
    assert "for" not in request.url.params
    assert isinstance(response, ChangesListResponse)
    assert [change.id for change in response.changes] == ["1"]


@pytest.mark.asyncio
async def test_list_changes_serialises_select_and_for():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json=envelope([change_payload(ready=True)]))

    client = make_client(handler)

    await client.changes.list_changes(select="ready", for_snap="hello-world")

    params = captured["request"].url.params
    assert params["select"] == "ready"
    assert params["for"] == "hello-world"


@pytest.mark.asyncio
async def test_list_changes_parses_empty_array():
    client = make_client(lambda request: httpx.Response(200, json=envelope([])))

    response = await client.changes.list_changes(select="all")

    assert response.changes == []


@pytest.mark.asyncio
async def test_list_changes_parses_tasks_and_progress():
    task = {
        "id": "1",
        "kind": "download",
        "summary": "Download snap",
        "status": "Done",
        "progress": {"label": "Download", "done": 3, "total": 3},
        "log": ["fetched"],
        "spawn-time": SPAWN_TIME,
    }
    payload = change_payload(ready=True, tasks=[task])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=envelope([payload]))

    client = make_client(handler)

    response = await client.changes.list_changes()

    change = response.changes[0]
    assert change.tasks[0].progress.done == 3
    assert change.tasks[0].log == ["fetched"]


@pytest.mark.asyncio
async def test_get_change_uses_change_id_in_path():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(
            200, json=envelope(change_payload(change_id="42", ready=True))
        )

    client = make_client(handler)

    response = await client.changes.get("42")

    assert captured["request"].url.path == "/v2/changes/42"
    assert isinstance(response, ChangesResponse)
    assert response.ready is True
    assert response.result.id == "42"


@pytest.mark.asyncio
async def test_get_change_accepts_change_without_tasks():
    # snapd tags tasks with omitempty: a taskless change has no "tasks" key.
    payload = change_payload(ready=True, status="Hold")
    del payload["tasks"]

    client = make_client(lambda request: httpx.Response(200, json=envelope(payload)))

    response = await client.changes.get("1")

    assert response.result.tasks == []


@pytest.mark.asyncio
async def test_abort_posts_abort_action_and_returns_current_change():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(
            200, json=envelope(change_payload(status="Abort", tasks=[]))
        )

    client = make_client(handler)

    response = await client.changes.abort("7")

    request = captured["request"]
    assert request.method == "POST"
    assert request.url.path == "/v2/changes/7"
    assert json.loads(request.content) == {"action": "abort"}
    assert isinstance(response, ChangesResponse)
    assert response.result.status == "Abort"
    assert response.ready is False


@pytest.mark.asyncio
async def test_abort_already_ready_raises_snapd_error():
    message = "cannot abort change 7 with nothing pending"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "status-code": 400,
                "type": "error",
                "status": "Bad Request",
                "result": error_payload(message),
            },
        )

    client = make_client(handler)

    with pytest.raises(SnapdAPIError) as excinfo:
        await client.changes.abort("7")

    assert excinfo.value.status_code == 400
    assert message in excinfo.value.message
    # Plain BadRequest responses carry no kind.
    assert excinfo.value.kind is None


@pytest.mark.asyncio
async def test_snap_client_delegates_single_change_to_component():
    calls: list[str] = []

    client = SnapClient(version="v2")

    async def fake_get(change_id: str) -> ChangesResponse:
        calls.append(change_id)
        return ChangesResponse.model_validate(envelope(change_payload(change_id)))

    client.changes.get = fake_get

    response = await client.get_changes_by_id("9")

    assert calls == ["9"]
    assert response.result.id == "9"


@pytest.mark.asyncio
async def test_change_generator_delegates_until_ready():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        if request.url.path == "/v2/changes/1":
            calls += 1
            payload = change_payload(ready=calls >= 2)
            return httpx.Response(200, json=envelope(payload))
        raise AssertionError(f"unexpected request {request.url}")

    client = make_client(handler)

    seen: list[ChangesResponse] = []
    async for change in client.get_changes_by_id_generator("1", poll_interval=0.001):
        seen.append(change)

    assert len(seen) == 2
    assert seen[-1].ready is True
    assert calls == 2
