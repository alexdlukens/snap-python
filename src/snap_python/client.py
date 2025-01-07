import asyncio
import logging
from typing import AsyncGenerator

import httpx
from retry import retry

from snap_python.components.config import ConfigEndpoints
from snap_python.components.snaps import SnapsEndpoints
from snap_python.components.store import StoreEndpoints
from snap_python.schemas.changes import ChangesResponse
from snap_python.utils import AbstractSnapsClient

SNAPD_SOCKET = "/run/snapd.socket"

logger = logging.getLogger("snap_python.client")
logger.setLevel(logging.DEBUG)


class SnapClient(AbstractSnapsClient):
    """Core class for interacting with the Snap Store and Snapd."""

    def __init__(
        self,
        version: str = "v2",
        snapd_socket_location: str = None,
        tcp_location: str = None,
        store_base_url: str = "https://api.snapcraft.io",
        store_headers: dict[str, str] = None,
        prompt_for_authentication: bool = False,
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

        self.snapd_headers = {}
        if prompt_for_authentication:
            self.snapd_headers = {"X-Allow-Interaction": "true"}

        self.version = version
        self.store_base_url = store_base_url
        self.store_headers = store_headers
        self.snapd_client = httpx.AsyncClient(
            transport=self._transport, headers=self.snapd_headers
        )
        self.snaps = SnapsEndpoints(self)
        self.store = StoreEndpoints(
            base_url=self.store_base_url,
            version=self.version,
            headers=self.store_headers,
        )
        self.config = ConfigEndpoints(self)
        self.snapd_client = httpx.AsyncClient(transport=self._transport)

    @retry(httpx.HTTPError, tries=3, delay=1, backoff=1)
    async def request(self, method: str, endpoint: str, **kwargs) -> httpx.Response:
        """
        Sends an HTTP request to the specified endpoint using the given method and parameters.
        Args:
            method (str): The HTTP method to use for the request (e.g., 'GET', 'POST').
            endpoint (str): The API endpoint to send the request to.
            **kwargs: Additional keyword arguments to pass to the request.
        Returns:
            httpx.Response: The response object from the HTTP request.
        Raises:
            httpx.HTTPStatusError: If the response contains an HTTP status code indicating an error.
        """

        response = await self.snapd_client.request(
            method, f"{self._base_url}/{self.version}/{endpoint}", **kwargs
        )
        response.raise_for_status()
        return response

    @retry(httpx.HTTPError, tries=3, delay=1, backoff=1)
    async def request_raw(self, method: str, endpoint: str, **kwargs) -> httpx.Response:
        """
        Sends an HTTP request using the specified method and endpoint.
        Args:
            method (str): The HTTP method to use for the request (e.g., 'GET', 'POST').
            endpoint (str): The endpoint URL to send the request to.
            **kwargs: Additional keyword arguments to pass to the request.
        Returns:
            httpx.Response: The response object resulting from the HTTP request.
        Raises:
            httpx.HTTPStatusError: If the response contains an HTTP status code indicating an error.
        """

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
        """
        Asynchronously retrieves changes by their ID.
        Args:
            change_id (str): The ID of the change to retrieve.
        Returns:
            ChangesResponse: The response object containing the changes.
        Raises:
            httpx.HTTPStatusError: If the request results in an HTTP error.
        """

        try:
            response = await self.request("GET", f"changes/{change_id}")
        except httpx.HTTPStatusError as e:
            logger.warning(
                "Bad response status code for get_changes_by_id: %s",
                e.response.status_code,
            )
            response = e.response

        return ChangesResponse.model_validate_json(response.content)

    async def get_changes_by_id_generator(
        self, change_id: str
    ) -> AsyncGenerator[ChangesResponse, None]:
        """
        Asynchronous generator to fetch changes by change ID.
        This generator continuously requests changes from the server using the provided
        change ID and yields the response as a ChangesResponse object. It includes error
        handling for HTTP status errors and adds a small delay between requests to avoid
        overwhelming the server.
        Args:
            change_id (str): The ID of the change to fetch.
        Yields:
            ChangesResponse: The response object containing the changes.
        Raises:
            httpx.HTTPStatusError: If the request fails with an HTTP status error.
        """
        while True:
            try:
                response = await self.request("GET", f"changes/{change_id}")
            except httpx.HTTPStatusError as e:
                logger.warning(
                    "Bad response status code for get_changes_by_id: %s",
                    e.response.status_code,
                )
                response = e.response

            change_response = ChangesResponse.model_validate_json(response.content)
            yield change_response

            await asyncio.sleep(
                0.01
            )  # Add a delay to avoid spamming the server with requests
