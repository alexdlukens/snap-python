import logging

import httpx
from retry import retry

from snap_python.components.snaps import SnapsEndpoints
from snap_python.components.store import StoreEndpoints
from snap_python.schemas.changes import ChangesResponse
from snap_python.utils import AbstractSnapsClient

SNAPD_SOCKET = "/run/snapd.socket"

logger = logging.getLogger("snap_python.client")
logger.setLevel(logging.DEBUG)


class SnapClient(AbstractSnapsClient):
    def __init__(
        self,
        version: str = "v2",
        snapd_socket_location: str = None,
        tcp_location: str = None,
        store_base_url: str = "https://api.snapcraft.io",
        store_headers: dict[str, str] = None,
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

        if store_headers is None:
            store_headers = {"Snap-Device-Series": "16", "X-Ubuntu-Series": "16"}

        self.version = version
        self.store_base_url = store_base_url
        self.store_headers = store_headers
        self.snapd_client = httpx.AsyncClient(transport=self._transport)
        self.snaps = SnapsEndpoints(self)
        self.store = StoreEndpoints(
            base_url=self.store_base_url,
            version=self.version,
            headers=self.store_headers,
        )

    @retry(httpx.HTTPError, tries=3, delay=1, backoff=1)
    async def request(self, method: str, endpoint: str, **kwargs) -> httpx.Response:
        response = await self.snapd_client.request(
            method, f"{self._base_url}/{self.version}/{endpoint}", **kwargs
        )
        logger.debug(f"response: {response.content}")
        response.raise_for_status()
        return response

    @retry(httpx.HTTPError, tries=3, delay=1, backoff=1)
    async def request_raw(self, method: str, endpoint: str, **kwargs) -> httpx.Response:
        response = await self.snapd_client.request(method, endpoint, **kwargs)

        response.raise_for_status()
        return response

    async def ping(self) -> httpx.Response:
        """Reserved for human-readable content describing the service.

        Returns:
            httpx.Response: _description_
        """
        response = await self.snapd_client.get(f"{self._base_url}/")

        return response

    async def get_changes_by_id(self, change_id: str) -> ChangesResponse:
        try:
            response = await self.request("GET", f"changes/{change_id}")
        except httpx.HTTPStatusError as e:
            logger.warning(
                f"Bad response status code for get_changes_by_id: {e.response.status_code}"
            )
            response = e.response
            pass

        return ChangesResponse.model_validate_json(response.content)
