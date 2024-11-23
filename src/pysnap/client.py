import httpx

from pysnap.components.snaps import SnapsEndpoints
from pysnap.utils import AbstractSnapsClient

SNAPD_SOCKET = "/run/snapd.socket"


class SnapClient(AbstractSnapsClient):
    def __init__(self, version: str = "v2"):
        self.version = version
        self._base_url = "http://localhost"
        self._transport = httpx.AsyncHTTPTransport(uds=SNAPD_SOCKET)
        self.client = httpx.AsyncClient(transport=self._transport)

        self.snaps = SnapsEndpoints(self)

    async def request(self, method: str, endpoint: str, **kwargs) -> httpx.Response:
        response = await self.client.request(
            method, f"{self._base_url}/{self.version}/{endpoint}", **kwargs
        )

        response.raise_for_status()
        return response

    async def request_raw(self, method: str, endpoint: str, **kwargs) -> httpx.Response:
        response = await self.client.request(method, endpoint, **kwargs)

        response.raise_for_status()
        return response

    async def ping(self) -> httpx.Response:
        """Reserved for human-readable content describing the service.

        Returns:
            httpx.Response: _description_
        """
        response = await self.client.get(f"{self._base_url}/")

        return response
