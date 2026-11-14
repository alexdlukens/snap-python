import httpx
import pytest

from snap_python.components.snaps import SnapsEndpoints
from snap_python.schemas.common import BaseErrorResult
from snap_python.schemas.snaps import InstalledSnap
from snap_python.utils import AbstractSnapsClient, SnapdAPIError

NOT_FOUND_BODY = {
    "status-code": 404,
    "type": "error",
    "status": "Not Found",
    "result": {"message": 'snap "banana" not found'},
}


def http_error(status_code: int, body: dict) -> httpx.HTTPStatusError:
    response = httpx.Response(
        status_code,
        json=body,
        request=httpx.Request("GET", "http://snapd.test/v2/snaps/banana"),
    )
    return httpx.HTTPStatusError("error", request=response.request, response=response)


class StatusClient(AbstractSnapsClient):
    """Client stub returning a fixed status code for every request."""

    def __init__(self, status_code: int, body: dict):
        self.status_code = status_code
        self.body = body

    async def request(self, method: str, endpoint: str, **kwargs) -> httpx.Response:
        response = httpx.Response(
            self.status_code,
            json=self.body,
            request=httpx.Request(method, f"http://snapd.test/v2/{endpoint}"),
        )
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error", request=response.request, response=response
            )
        return response

    async def request_raw(self, method: str, endpoint: str, **kwargs):
        return await self.request(method, endpoint, **kwargs)

    async def get_changes_by_id(self, change_id):  # pragma: no cover
        raise NotImplementedError


@pytest.mark.asyncio
async def test_get_snap_info_returns_error_model_on_404():
    snaps = SnapsEndpoints(StatusClient(404, NOT_FOUND_BODY))

    response = await snaps.get_snap_info("banana")

    assert response.status_code == 404
    assert isinstance(response.result, BaseErrorResult)
    assert response.result.message == 'snap "banana" not found'


@pytest.mark.asyncio
async def test_get_snap_info_raises_on_500():
    body = {
        "status-code": 500,
        "type": "error",
        "status": "Internal Error",
        "result": {"message": "boom"},
    }
    snaps = SnapsEndpoints(StatusClient(500, body))

    with pytest.raises(SnapdAPIError, match="500"):
        await snaps.get_snap_info("banana")


@pytest.mark.asyncio
async def test_get_snap_info_raises_on_403():
    body = {
        "status-code": 403,
        "type": "error",
        "status": "Forbidden",
        "result": {"message": "access denied"},
    }
    snaps = SnapsEndpoints(StatusClient(403, body))

    with pytest.raises(SnapdAPIError, match="403"):
        await snaps.get_snap_info("banana")


@pytest.mark.asyncio
async def test_get_installed_snap_none_on_404():
    snaps = SnapsEndpoints(StatusClient(404, NOT_FOUND_BODY))
    assert await snaps.get_installed_snap("banana") is None


@pytest.mark.asyncio
async def test_get_installed_snap_raises_on_500():
    body = {
        "status-code": 500,
        "type": "error",
        "status": "Internal Error",
        "result": {"message": "boom"},
    }
    snaps = SnapsEndpoints(StatusClient(500, body))

    with pytest.raises(SnapdAPIError):
        await snaps.get_installed_snap("banana")


@pytest.mark.asyncio
async def test_get_installed_snap_returns_model():
    body = {
        "status-code": 200,
        "type": "sync",
        "status": "OK",
        "result": {
            "name": "hello-world",
            "revision": "29",
            "channel": "stable",
            "ignore-validation": False,
            "installed-size": 1024,
            "jailmode": False,
            "mounted-from": "/var/lib/snapd/snaps/hello-world_29.snap",
            "status": "active",
        },
    }
    snaps = SnapsEndpoints(StatusClient(200, body))

    result = await snaps.get_installed_snap("hello-world")

    assert isinstance(result, InstalledSnap)
    assert result.name == "hello-world"
    assert await snaps.is_snap_installed("hello-world") is True
