import httpx

from pysnap.components.snaps import SnapsEndpoints
from pysnap.utils import AbstractSnapsClient

SNAPD_SOCKET = "/run/snapd.socket"


class SnapClient(AbstractSnapsClient):
    def __init__(
        self,
        version: str = "v2",
        snapd_socket_location: str = None,
        tcp_location: str = None,
    ):
        if tcp_location and snapd_socket_location:
            raise ValueError(
                "Only one of snapd_socket_location or tcp_location can be provided."
            )
        if tcp_location is not None:
            self._base_url = tcp_location
            self._transport = httpx.AsyncHTTPTransport()
        else:
            self._base_url = "http://localhost"
            self._transport = httpx.AsyncHTTPTransport(
                uds=snapd_socket_location or SNAPD_SOCKET
            )

        self.version = version
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

    async def get_changes_by_id(self, change_id: str) -> httpx.Response:
        response = await self.request("GET", f"changes/{change_id}")

        return response
