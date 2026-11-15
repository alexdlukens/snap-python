import asyncio
import time
from typing import AsyncGenerator, Literal

import httpx

from snap_python.schemas.changes import ChangesListResponse, ChangesResponse
from snap_python.schemas.common import BaseErrorResult
from snap_python.utils import AbstractSnapsClient, SnapdAPIError, async_retry

#: Values ``GET /v2/changes`` accepts for ``select``.
ChangeSelect = Literal["all", "in-progress", "ready"]


class ChangeEndpoints:
    """Endpoints under ``/v2/changes``.

    :param client: Client used to talk to snapd.
    """

    def __init__(self, client: AbstractSnapsClient) -> None:
        self._client = client
        self.common_endpoint = "changes"

    @async_retry(httpx.HTTPError, tries=3, delay=0.5)
    async def get(self, change_id: str) -> ChangesResponse:
        """
        Retrieve a single change.

        :param change_id: The ID of the change to retrieve.
        :type change_id: str

        :returns: The response object containing the change.
        :rtype: ChangesResponse

        :raises SnapdAPIError: If snapd does not know the change (404
            ``cannot find change with id ...``).
        :raises httpx.HTTPStatusError: If the request results in an HTTP error.
        """
        response = await self._client.request(
            "GET", f"{self.common_endpoint}/{change_id}"
        )
        return ChangesResponse.model_validate_json(response.content)

    async def list_changes(
        self,
        select: ChangeSelect | None = None,
        for_snap: str | None = None,
    ) -> ChangesListResponse:
        """
        Retrieve changes, optionally filtered by state and snap name.

        :param select: ``"all"``, ``"in-progress"`` or ``"ready"``. None
            (default) omits the parameter, so snapd applies its own default,
            ``"in-progress"``. Any other value is rejected by snapd with a 400.
        :type select: str, optional
        :param for_snap: Only return changes recorded against this snap name.
            snapd matches the ``snap-names`` change data, splitting
            ``"<snap>.<app>"`` entries on the snap part. None (default) returns
            changes for every snap. Sent as the ``for`` query parameter.
        :type for_snap: str, optional

        :returns: The response object containing the list of changes.
        :rtype: ChangesListResponse

        :raises SnapdAPIError: If snapd rejects the request, for example for an
            unknown ``select`` value.
        :raises httpx.HTTPStatusError: If the request results in an HTTP error.
        """
        params: dict[str, str] = {}
        if select is not None:
            params["select"] = select
        if for_snap is not None:
            params["for"] = for_snap

        response = await self._client.request(
            "GET", self.common_endpoint, params=params
        )
        return ChangesListResponse.model_validate_json(response.content)

    async def abort(self, change_id: str) -> ChangesResponse:
        """
        Abort a pending change.

        The request itself is synchronous: snapd flags the change and returns
        its current info with HTTP 200 straight away. The abort then proceeds
        asynchronously, so the returned change is usually still in
        ``"Doing"``/``"Abort"`` state; poll it to observe completion.

        :param change_id: The ID of the change to abort.
        :type change_id: str

        :returns: The response object containing the current change info.
        :rtype: ChangesResponse

        :raises SnapdAPIError: If snapd rejects the abort, for example with 400
            ``cannot abort change <id> with nothing pending`` when the change
            is already ready, or 404 for an unknown change.
        :raises httpx.HTTPStatusError: If the request results in an HTTP error.
        """
        response = await self._client.request(
            "POST",
            f"{self.common_endpoint}/{change_id}",
            json={"action": "abort"},
        )
        return ChangesResponse.model_validate_json(response.content)

    async def watch(
        self,
        change_id: str,
        timeout: float | None = None,
        poll_interval: float = 0.5,
    ) -> AsyncGenerator[ChangesResponse, None]:
        """
        Poll a change until it is ready.

        :param change_id: The ID of the change to poll.
        :type change_id: str
        :param timeout: Maximum number of seconds to poll. None (default)
            polls until the change is ready.
        :type timeout: float | None
        :param poll_interval: Seconds between two polls.
        :type poll_interval: float

        :yields: Every :class:`ChangesResponse`, the ready one last.
        :rtype: ChangesResponse

        :raises SnapdAPIError: If the change reports an error or the timeout
            expires.
        :raises httpx.HTTPStatusError: If a poll fails with an HTTP error.
        """
        deadline = None if timeout is None else time.monotonic() + timeout

        while True:
            change_response = await self.get(change_id)

            if isinstance(change_response.result, BaseErrorResult):
                raise SnapdAPIError(
                    f"Error waiting for change {change_id}: "
                    f"{change_response.result.message}"
                )
            if change_response.result.err:
                raise SnapdAPIError(
                    f"Error waiting for change {change_id}: "
                    f"{change_response.result.err}"
                )

            yield change_response

            if change_response.ready:
                return

            if deadline is not None and time.monotonic() >= deadline:
                raise SnapdAPIError(
                    f"Timed out after {timeout}s waiting for change {change_id}"
                )
            await asyncio.sleep(poll_interval)
