import logging
from typing import AsyncGenerator

import httpx

from snap_python.components.changes import ChangeEndpoints
from snap_python.components.config import ConfigEndpoints
from snap_python.components.interfaces import InterfacesEndpoints
from snap_python.components.logs import LogsEndpoints
from snap_python.components.snaps import SnapsEndpoints
from snap_python.components.store import StoreEndpoints
from snap_python.schemas.changes import ChangesResponse
from snap_python.utils import (
    IDEMPOTENT_HTTP_METHODS,
    AbstractSnapsClient,
    SnapdAPIError,
    async_retry,
    is_transient_exception,
)

SNAPD_SOCKET = "/run/snapd.socket"

logger = logging.getLogger("snap_python.client")


def _is_retryable_request(exc: BaseException, args: tuple, kwargs: dict) -> bool:
    """Retry predicate for :meth:`SnapClient.request` and :meth:`request_raw`.

    Only idempotent methods are retried: replaying a POST/PUT/DELETE can
    duplicate side effects (installing a snap twice, for instance).
    """
    method = kwargs.get("method")
    if method is None and len(args) >= 2:
        method = args[1]
    if str(method).upper() not in IDEMPOTENT_HTTP_METHODS:
        return False
    return is_transient_exception(exc)


def _snapd_error_from_response(response: httpx.Response) -> SnapdAPIError | None:
    """Build a :class:`SnapdAPIError` from a snapd error envelope.

    snapd reports failures as
    ``{"type": "error", "status-code": N, "result": {"message", "kind", "value"}}``.
    Returns ``None`` when the body is not such an envelope, so callers can fall
    back to :meth:`httpx.Response.raise_for_status`.
    """
    try:
        body = response.json()
    except ValueError:
        return None
    if not isinstance(body, dict) or body.get("type") != "error":
        return None
    result = body.get("result")
    if not isinstance(result, dict):
        return None

    request = response.request
    request_desc = (
        f"{request.method} {request.url}" if request is not None else "snapd request"
    )
    detail = result.get("message") or "snapd returned an error"
    return SnapdAPIError(
        f"HTTP {response.status_code} for {request_desc}: {detail}",
        status_code=response.status_code,
        kind=result.get("kind"),
        value=result.get("value"),
        response=response,
    )


class SnapClient(AbstractSnapsClient):
    """Core class for interacting with the Snap Store and Snapd.

    :param timeout: Timeout applied to every snapd request, in seconds or as an
        :class:`httpx.Timeout`. ``None`` disables the timeout (httpx interprets
        it that way), which is useful for large sideloads. Defaults to 60.0;
        httpx's own 5 second default is too short for uploads.
    """

    def __init__(
        self,
        version: str = "v2",
        snapd_socket_location: str = None,
        tcp_location: str = None,
        store_base_url: str = "https://api.snapcraft.io",
        store_headers: dict[str, str] = None,
        prompt_for_authentication: bool = False,
        timeout: float | httpx.Timeout | None = 60.0,
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
            transport=self._transport, headers=self.snapd_headers, timeout=timeout
        )
        self.snaps = SnapsEndpoints(self)
        self.store = StoreEndpoints(
            base_url=self.store_base_url,
            version=self.version,
            headers=self.store_headers,
        )
        self.config = ConfigEndpoints(self)
        self.changes = ChangeEndpoints(self)
        self.interfaces = InterfacesEndpoints(self)
        self.logs = LogsEndpoints(self)

    def endpoint_url(self, endpoint: str) -> str:
        """
        Build the absolute URL of a snapd ``/v2`` endpoint.

        :param endpoint: Endpoint relative to ``/v2/``, for example ``"logs"``.
        :type endpoint: str

        :returns: The absolute URL, using the configured base URL and version.
        :rtype: str
        """
        return f"{self._base_url}/{self.version}/{endpoint}"

    @async_retry(
        httpx.HTTPError, tries=3, delay=1, backoff=1, retry_if=_is_retryable_request
    )
    async def request(self, method: str, endpoint: str, **kwargs) -> httpx.Response:
        r"""
        Sends an HTTP request to the specified endpoint using the given method and parameters.

        :param method: The HTTP method to use for the request (e.g., 'GET', 'POST').
        :type method: str
        :param endpoint: The API endpoint to send the request to.
        :type endpoint: str
        :param `**kwargs`: Additional keyword arguments to pass to the request.

        :returns: The response object from the HTTP request.
        :rtype: httpx.Response

        :raises SnapdAPIError: If snapd answered with an error envelope; the
            parsed ``kind`` and ``value`` are available on the exception.
        :raises httpx.HTTPStatusError: If the response contains an HTTP status
            code indicating an error and the body is not a snapd envelope.
        """

        response = await self.snapd_client.request(
            method, self.endpoint_url(endpoint), **kwargs
        )
        if response.is_error:
            snapd_error = _snapd_error_from_response(response)
            if snapd_error is not None:
                raise snapd_error
        response.raise_for_status()
        return response

    @async_retry(
        httpx.HTTPError, tries=3, delay=1, backoff=1, retry_if=_is_retryable_request
    )
    async def request_raw(self, method: str, endpoint: str, **kwargs) -> httpx.Response:
        r"""
        Sends an HTTP request using the specified method and endpoint.

        :param method: The HTTP method to use for the request (e.g., 'POST').
        :type method: str
        :param endpoint: The endpoint URL to send the request to.
        :type endpoint: str
        :param `**kwargs`: Additional keyword arguments to pass to the request.

        :returns: The response object resulting from the HTTP request.
        :rtype: httpx.Response

        :raises SnapdAPIError: If snapd answered with an error envelope; the
            parsed ``kind`` and ``value`` are available on the exception.
        :raises httpx.HTTPStatusError: If the response contains an HTTP status
            code indicating an error and the body is not a snapd envelope.
        """

        response = await self.snapd_client.request(method, endpoint, **kwargs)

        if response.is_error:
            snapd_error = _snapd_error_from_response(response)
            if snapd_error is not None:
                raise snapd_error
        response.raise_for_status()
        return response

    async def ping(self) -> httpx.Response:
        """
        Reserved for human-readable content describing the service.

        :returns: The response from the ping request.
        :rtype: httpx.Response

        :raises httpx.HTTPStatusError: If snapd is not reachable or reports an
            error status.
        """
        response = await self.snapd_client.get(f"{self._base_url}/")
        response.raise_for_status()

        return response

    async def is_available(self) -> bool:
        """
        Check whether snapd is reachable and healthy.

        :returns: True if snapd answered with a 2xx status, False otherwise.
        :rtype: bool
        """
        try:
            await self.ping()
        except httpx.HTTPError as exc:
            logger.debug("snapd is not available: %s", exc)
            return False
        return True

    async def close(self) -> None:
        """Close the underlying snapd and store HTTP clients."""
        await self.snapd_client.aclose()
        await self.store.close()

    async def __aenter__(self) -> "SnapClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def get_changes_by_id(self, change_id: str) -> ChangesResponse:
        """
        Asynchronously retrieves changes by their ID.

        Thin delegate to :meth:`snap_python.components.changes.ChangeEndpoints.get`.

        :param change_id: The ID of the change to retrieve.
        :type change_id: str

        :returns: The response object containing the changes.
        :rtype: ChangesResponse

        :raises httpx.HTTPStatusError: If the request results in an HTTP error.
        """
        return await self.changes.get(change_id)

    async def get_changes_by_id_generator(
        self,
        change_id: str,
        timeout: float | None = None,
        poll_interval: float = 0.5,
    ) -> AsyncGenerator[ChangesResponse, None]:
        """
        Asynchronous generator to fetch changes by change ID.

        Thin delegate to
        :meth:`snap_python.components.changes.ChangeEndpoints.watch`: polls
        snapd and yields every :class:`ChangesResponse` until the change is
        ready. Error results are raised instead of being yielded silently.

        :param change_id: The ID of the change to fetch.
        :type change_id: str
        :param timeout: Maximum number of seconds to poll. ``None`` polls until
            the change is ready.
        :type timeout: float | None
        :param poll_interval: Seconds between two polls.
        :type poll_interval: float

        :yields: The response object containing the changes.
        :rtype: ChangesResponse

        :raises SnapdAPIError: If the change reports an error or the timeout
            expires.
        :raises httpx.HTTPStatusError: If the request fails with an HTTP error.
        """
        async for change_response in self.changes.watch(
            change_id, timeout=timeout, poll_interval=poll_interval
        ):
            yield change_response

    async def get_system_info(self) -> dict:
        """
        Retrieves system information from the snapd service.

        :returns: A dictionary containing system information.
        :rtype: dict

        :raises httpx.HTTPStatusError: If the request results in an HTTP error.
        """
        response = await self.request("GET", "system-info")
        return response.json()
