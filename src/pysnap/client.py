import logging

import httpx
from pydantic import ValidationError

from pysnap.components.snaps import SnapsEndpoints
from pysnap.schemas.changes import ChangesResponse
from pysnap.utils import AbstractSnapsClient

SNAPD_SOCKET = "/run/snapd.socket"

logger = logging.getLogger("pysnap.client")
logger.setLevel(logging.DEBUG)


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

    async def get_changes_by_id(self, change_id: str) -> ChangesResponse:
        response = await self.request("GET", f"changes/{change_id}")

        try:
            response = ChangesResponse.model_validate_json(response.content)
        except ValidationError as ve:
            # print the error message and raise the exception
            with open("error.json", "w") as f:
                f.write(ve.json())
                logger.debug("Saved validation errors to: %s", f.name)
            raise ve

        return response
