import logging
from pathlib import Path
from typing import Any

import httpx

from snap_python.schemas.changes import ChangesResponse
from snap_python.schemas.common import AsyncResponse
from snap_python.schemas.snaps import (
    AppsResponse,
    InstalledSnap,
    InstalledSnapListResponse,
    SingleInstalledSnapResponse,
)
from snap_python.utils import AbstractSnapsClient, SnapdAPIError, wait_for_change

logger = logging.getLogger("snap_python.components.snaps")


class SnapsEndpoints:
    def __init__(self, client: AbstractSnapsClient) -> None:
        self._client = client
        self.common_endpoint = "snaps"

    async def _wait_for_change(
        self,
        change_id: str,
        timeout: float | None = None,
        poll_interval: float = 0.5,
        progress_callback=None,
    ) -> ChangesResponse:
        """Wait for a snapd change to reach a terminal state.

        Thin wrapper around :func:`snap_python.utils.wait_for_change` bound to
        this endpoint's client.

        :param change_id: The change to wait for.
        :type change_id: str
        :param timeout: Maximum number of seconds to wait, None waits forever.
        :type timeout: float, optional
        :param poll_interval: Seconds between two polls.
        :type poll_interval: float, optional
        :param progress_callback: Optional callable receiving intermediate changes.
        :type progress_callback: callable, optional

        :returns: The final change response.
        :rtype: ChangesResponse

        :raises SnapdAPIError: If the change reports an error or times out.
        """
        return await wait_for_change(
            self._client,
            change_id,
            timeout=timeout,
            poll_interval=poll_interval,
            progress_callback=progress_callback,
        )

    async def list_installed_snaps(self) -> InstalledSnapListResponse:
        """
        Asynchronously retrieves a list of installed snaps.

        :returns: The response containing the list of installed snaps.
        :rtype: InstalledSnapListResponse

        :raises httpx.HTTPStatusError: If the response status code does not indicate success.
        """

        response: httpx.Response = await self._client.request(
            "GET", self.common_endpoint
        )

        if response.status_code > 299:
            raise httpx.HTTPStatusError(
                request=response.request,
                response=response,
                message=f"Invalid status code in response: {response.status_code}",
            )
        return InstalledSnapListResponse.model_validate_json(response.content)

    async def get_snap_info(self, snap: str) -> SingleInstalledSnapResponse:
        """
        Retrieves information about a specific snap.

        :param snap: The name of the snap to retrieve information for.
        :type snap: str

        :returns: The response containing information about the snap.
        :rtype: SingleInstalledSnapResponse

        :raises httpx.HTTPStatusError: If the response status code does not indicate success.
        """
        try:
            response: httpx.Response = await self._client.request(
                "GET", f"{self.common_endpoint}/{snap}"
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code != httpx.codes.NOT_FOUND:
                logger.debug(
                    "Bad status code from get_snap_info on snap %s: %s",
                    snap,
                    e.response.status_code,
                )
                if isinstance(e, SnapdAPIError):
                    # Already carries the parsed kind/value envelope.
                    raise
                raise SnapdAPIError(
                    f"Failed to get info for snap {snap}: "
                    f"HTTP {e.response.status_code}",
                    response=e.response,
                ) from e
            logger.debug("Snap %s is not installed (HTTP 404)", snap)
            return SingleInstalledSnapResponse.model_validate_json(e.response.content)

        return SingleInstalledSnapResponse.model_validate_json(response.content)

    async def get_installed_snap(self, snap: str) -> InstalledSnap | None:
        """
        Get information about an installed snap.

        :param snap: The name of the snap to inspect.
        :type snap: str

        :returns: The installed snap, or None if the snap is not installed.
        :rtype: InstalledSnap | None

        :raises SnapdAPIError: If snapd reports an unexpected error.
        """
        response = await self.get_snap_info(snap)
        if isinstance(response.result, InstalledSnap):
            return response.result
        if response.status_code == httpx.codes.NOT_FOUND:
            return None
        raise SnapdAPIError(
            f"Unexpected response while getting snap {snap}: "
            f"HTTP {response.status_code}"
        )

    async def is_snap_installed(self, snap: str) -> bool:
        """
        Check if a snap package is installed.

        :param snap: The name of the snap package to check.
        :type snap: str

        :returns: True if the snap package is installed, False otherwise.
        :rtype: bool
        """

        return await self.get_installed_snap(snap) is not None

    @staticmethod
    def _sideload_form_data(
        filename: str,
        channel: str | None = None,
        classic: bool = False,
        dangerous: bool = False,
        devmode: bool = False,
        jailmode: bool = False,
    ) -> dict[str, str]:
        """Build the multipart form snapd honors for a sideload.

        The daemon's multipart handler (``sideloadOrTrySnap`` in
        ``daemon/api_sideload_n_try.go``) only special-cases ``action ==
        "try"``; every other action is a path install. These field names match
        what snapd's own client writes (``client/snap_op.go``).

        :param filename: Path to the snap file, sent as ``snap-path``.
        :type filename: str
        :param channel: Optional channel to send with the sideload.
        :type channel: str, optional
        :param classic: Whether to request classic confinement.
        :type classic: bool
        :param dangerous: Whether to allow unasserted snaps.
        :type dangerous: bool
        :param devmode: Whether to request devmode.
        :type devmode: bool
        :param jailmode: Whether to request jailmode.
        :type jailmode: bool

        :returns: Form fields to send alongside the ``snap`` file part.
        :rtype: dict[str, str]
        """
        form_data = {"action": "install", "snap-path": filename}
        if channel is not None:
            form_data["channel"] = channel
        for key, value in (
            ("classic", classic),
            ("dangerous", dangerous),
            ("devmode", devmode),
            ("jailmode", jailmode),
        ):
            if value:
                form_data[key] = "true"
        return form_data

    async def install_snap(
        self,
        snap: str,
        channel: str | None = None,
        classic: bool = False,
        dangerous: bool = False,
        devmode: bool = False,
        jailmode: bool = False,
        revision: int = None,
        filename: str = None,
        wait: bool = False,
        timeout: float | None = None,
    ) -> AsyncResponse | ChangesResponse:
        """
        Install or sideload a snap.

        To sideload a snap, provide the filename parameter with the path to the snap file.
        snapd accepts a locally injected snap whose assertion is valid without
        ``dangerous``; that flag is only needed for unasserted snaps and is
        passed through untouched.

        :param snap: Name of the snap to install.
        :type snap: str
        :param channel: Channel to install from. None (default) lets snapd use
            its own default channel.
        :type channel: str, optional
        :param classic: Install with classic confinement, defaults to False.
        :type classic: bool, optional
        :param dangerous: Install the given snap files even if there are no pre-acknowledged signatures for them, meaning they are not verified and could be dangerous if true (optional, implied by devmode), defaults to False.
        :type dangerous: bool, optional
        :param devmode: Install with devmode, defaults to False.
        :type devmode: bool, optional
        :param jailmode: Install snap with jailmode, defaults to False.
        :type jailmode: bool, optional
        :param revision: Install a specific revision of the snap, defaults to None.
        :type revision: int, optional
        :param filename: Path to snap to sideload, defaults to None.
        :type filename: str, optional
        :param wait: Whether to wait for snap to install. If not waiting, will return async response with change id, defaults to False.
        :type wait: bool, optional
        :param timeout: Maximum number of seconds to wait for the install to finish, defaults to None (wait forever).
        :type timeout: float, optional

        :raises FileNotFoundError: If the specified snap file does not exist.
        :raises SnapdAPIError: If there is an error during the snap install.

        :returns: If wait is True, will return ChangesResponse. Otherwise, will return AsyncResponse.
        :rtype: AsyncResponse | ChangesResponse
        """
        request_data = {
            "action": "install",
            "classic": classic,
            "dangerous": dangerous,
            "devmode": devmode,
            "jailmode": jailmode,
        }
        if channel is not None:
            request_data["channel"] = channel
        if revision:
            request_data["revision"] = revision
        if filename:
            # sideload
            snap_path = Path(filename)
            if not snap_path.exists():
                raise FileNotFoundError(f"File {filename} does not exist")
            form_data = self._sideload_form_data(
                filename=str(snap_path),
                channel=channel,
                classic=classic,
                dangerous=dangerous,
                devmode=devmode,
                jailmode=jailmode,
            )
            with open(snap_path, "rb") as snap_file:
                raw_response: httpx.Response = await self._client.request(
                    "POST",
                    f"{self.common_endpoint}",
                    data=form_data,
                    files={"snap": (snap_path.name, snap_file)},
                )
        else:
            # install from default snap store
            raw_response: httpx.Response = await self._client.request(
                "POST", f"{self.common_endpoint}/{snap}", json=request_data
            )
        response = AsyncResponse.model_validate_json(raw_response.content)
        if wait:
            return await self._wait_for_change(response.change, timeout=timeout)
        return response

    async def remove_snap(
        self,
        snap: str,
        purge: bool = False,
        terminate: bool = False,
        wait: bool = False,
        timeout: float | None = None,
    ) -> AsyncResponse | ChangesResponse:
        """
        Asynchronously removes a snap package.

        :param snap: The name of the snap package to remove.
        :type snap: str
        :param purge: If True, purges the snap package. Defaults to False.
        :type purge: bool, optional
        :param terminate: If True, terminates the snap package. Defaults to False.
        :type terminate: bool, optional
        :param wait: If True, waits for the removal process to complete. Defaults to False.
        :type wait: bool, optional
        :param timeout: Maximum number of seconds to wait for the removal to finish, defaults to None (wait forever).
        :type timeout: float, optional

        :returns: The response from the snapd API, either an asynchronous response or a changes response if waiting for completion.
        :rtype: AsyncResponse | ChangesResponse

        :raises SnapdAPIError: If there is an error in the snap removal process.
        """
        request_data = {
            "action": "remove",
            "purge": purge,
            "terminate": terminate,
        }

        raw_response: httpx.Response = await self._client.request(
            "POST", f"{self.common_endpoint}/{snap}", json=request_data
        )
        response = AsyncResponse.model_validate_json(raw_response.content)

        if wait:
            return await self._wait_for_change(response.change, timeout=timeout)

        return response

    async def refresh_snap(
        self,
        snap: str,
        channel: str | None = None,
        classic: bool = False,
        dangerous: bool = False,
        devmode: bool = False,
        ignore_validation: bool = False,
        jailmode: bool = False,
        revision: int = None,
        filename: str = None,
        wait: bool = False,
        timeout: float | None = None,
    ) -> AsyncResponse | ChangesResponse:
        """
        Refreshes a snap package.

        :param snap: The name of the snap package to refresh.
        :type snap: str
        :param channel: Channel to refresh from. None (default) keeps the
            currently tracked channel.
        :type channel: str, optional
        :param classic: Whether to use classic confinement. Defaults to False.
        :type classic: bool, optional
        :param dangerous: Whether to allow installation of unasserted snaps. Defaults to False.
        :type dangerous: bool, optional
        :param devmode: Whether to use development mode. Defaults to False.
        :type devmode: bool, optional
        :param ignore_validation: Whether to ignore validation. Defaults to False.
        :type ignore_validation: bool, optional
        :param jailmode: Whether to use jail mode. Defaults to False.
        :type jailmode: bool, optional
        :param revision: The specific revision to refresh to. Defaults to None.
        :type revision: int, optional
        :param filename: The path to the snap file for sideloading. Defaults to None.
        :type filename: str, optional
        :param wait: Whether to wait for the refresh operation to complete. Defaults to False.
        :type wait: bool, optional
        :param timeout: Maximum number of seconds to wait for the refresh to finish, defaults to None (wait forever).
        :type timeout: float, optional

        :returns: The response from the refresh operation.
        :rtype: AsyncResponse | ChangesResponse

        :raises FileNotFoundError: If the specified snap file does not exist.
        :raises SnapdAPIError: If there is an error during the snap refresh.
        """
        request_data = {
            "action": "refresh",
            "classic": classic,
            "dangerous": dangerous,
            "devmode": devmode,
            "ignore_validation": ignore_validation,
            "jailmode": jailmode,
        }
        if channel is not None:
            request_data["channel"] = channel
        if revision:
            request_data["revision"] = revision
        if filename:
            # Sideload. The daemon's multipart handler only treats
            # action == "try" specially; every other value is a path install,
            # so use "install" here instead of "refresh".
            snap_path = Path(filename)
            if not snap_path.exists():
                raise FileNotFoundError(f"File {filename} does not exist")
            form_data = self._sideload_form_data(
                filename=str(snap_path),
                channel=channel,
                classic=classic,
                dangerous=dangerous,
                devmode=devmode,
                jailmode=jailmode,
            )
            with open(snap_path, "rb") as snap_file:
                raw_response: httpx.Response = await self._client.request(
                    "POST",
                    f"{self.common_endpoint}",
                    data=form_data,
                    files={"snap": (snap_path.name, snap_file)},
                )
        else:
            # refresh from default snap store
            raw_response: httpx.Response = await self._client.request(
                "POST", f"{self.common_endpoint}/{snap}", json=request_data
            )
        response = AsyncResponse.model_validate_json(raw_response.content)
        if wait:
            return await self._wait_for_change(response.change, timeout=timeout)
        return response

    async def disable_snap(
        self,
        snap: str,
        wait: bool = False,
        timeout: float | None = None,
    ) -> AsyncResponse | ChangesResponse:
        """
        Disables a snap package.

        :param snap: The name of the snap package to disable.
        :type snap: str
        :param wait: Whether to wait for the disable operation to complete. Defaults to False.
        :type wait: bool, optional
        :param timeout: Maximum number of seconds to wait for the disable to finish, defaults to None (wait forever).
        :type timeout: float, optional

        :returns: The response from the disable operation.
        :rtype: AsyncResponse | ChangesResponse

        :raises SnapdAPIError: If there is an error during the snap disable operation.
        """
        request_data = {
            "action": "disable",
        }

        raw_response: httpx.Response = await self._client.request(
            "POST", f"{self.common_endpoint}/{snap}", json=request_data
        )
        response = AsyncResponse.model_validate_json(raw_response.content)

        if wait:
            return await self._wait_for_change(response.change, timeout=timeout)

        return response

    async def enable_snap(
        self,
        snap: str,
        wait: bool = False,
        timeout: float | None = None,
    ) -> AsyncResponse | ChangesResponse:
        """
        enables a snap package.

        :param snap: The name of the snap package to enable.
        :type snap: str
        :param wait: Whether to wait for the enable operation to complete. Defaults to False.
        :type wait: bool, optional
        :param timeout: Maximum number of seconds to wait for the enable to finish, defaults to None (wait forever).
        :type timeout: float, optional

        :returns: The response from the enable operation.
        :rtype: AsyncResponse | ChangesResponse

        :raises SnapdAPIError: If there is an error during the snap enable operation.
        """
        request_data = {
            "action": "enable",
        }

        raw_response: httpx.Response = await self._client.request(
            "POST", f"{self.common_endpoint}/{snap}", json=request_data
        )
        response = AsyncResponse.model_validate_json(raw_response.content)

        if wait:
            return await self._wait_for_change(response.change, timeout=timeout)

        return response

    async def get_snap_apps(
        self,
        snap: str,
        services_only: bool = False,
    ) -> AppsResponse:
        """
        Retrieves the applications associated with a specific snap.

        :param snap: The name of the snap to retrieve applications for.
        :type snap: str
        :param services_only: Whether to retrieve only service applications.
        :type services_only: bool

        :returns: The response containing the list of applications for the specified snap.
        :rtype: AppsResponse
        """

        payload: dict[str, Any] = {"names": [snap]}
        if services_only:
            payload["select"] = "service"

        response: httpx.Response = await self._client.request(
            "GET", "apps", params=payload
        )
        if response.status_code != 200:
            raise SnapdAPIError(f"Failed to retrieve apps for snap: {snap}")
        return AppsResponse.model_validate_json(response.content)
