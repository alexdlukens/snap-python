import asyncio
import logging
from pathlib import Path

import httpx

from snap_python.schemas.changes import ChangesResponse
from snap_python.schemas.common import AsyncResponse
from snap_python.schemas.snaps import (
    InstalledSnapListResponse,
    SingleInstalledSnapResponse,
)
from snap_python.utils import AbstractSnapsClient, SnapdAPIError, going_to_reload_daemon

logger = logging.getLogger("snap_python.components.snaps")


class SnapsEndpoints:
    def __init__(self, client: AbstractSnapsClient) -> None:
        self._client = client
        self.common_endpoint = "snaps"

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

        response = InstalledSnapListResponse.model_validate_json(response.content)
        if response.status_code > 299:
            raise httpx.HTTPStatusError(
                request=response.request,
                response=response,
                message=f"Invalid status code in response: {response.status_code}",
            )
        return response

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
            logger.debug(
                "Bad status code from get_snap_info on snap %s: %s",
                snap,
                e.response.status_code,
            )
            response = e.response

        return SingleInstalledSnapResponse.model_validate_json(response.content)

    async def is_snap_installed(self, snap: str) -> bool:
        """
        Check if a snap package is installed.

        :param snap: The name of the snap package to check.
        :type snap: str

        :returns: True if the snap package is installed, False otherwise.
        :rtype: bool
        """

        snap_info = await self.get_snap_info(snap)
        if snap_info.status == "OK":
            return True
        return False

    async def install_snap(
        self,
        snap: str,
        channel: str = "stable",
        classic: bool = False,
        dangerous: bool = False,
        devmode: bool = False,
        jailmode: bool = False,
        revision: int = None,
        filename: str = None,
        wait: bool = False,
    ) -> AsyncResponse | ChangesResponse:
        """
        Install or sideload a snap.

        To sideload a snap, provide the filename parameter with the path to the snap file.

        :param snap: Name of the snap to install.
        :type snap: str
        :param channel: Channel to install, defaults to "stable".
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

        :raises FileNotFoundError: If the specified snap file does not exist.
        :raises ValueError: If attempting to sideload without the dangerous flag set to True.
        :raises SnapdAPIError: If there is an error during the snap install.

        :returns: If wait is True, will return ChangesResponse. Otherwise, will return AsyncResponse.
        :rtype: AsyncResponse | ChangesResponse
        """
        request_data = {
            "action": "install",
            "channel": channel,
            "classic": classic,
            "dangerous": dangerous,
            "devmode": devmode,
            "jailmode": jailmode,
        }
        if revision:
            request_data["revision"] = revision
        if filename:
            # sideload
            if not Path(filename).exists():
                raise FileNotFoundError(f"File {filename} does not exist")
            if request_data.get("dangerous") is not True:
                raise ValueError(
                    "Cannot sideload snap without dangerous flag set to True"
                )
            raw_response: httpx.Response = await self._client.request(
                "POST",
                f"{self.common_endpoint}",
                data=request_data,
                files={"snap": open(filename, "rb")},
            )
        else:
            # install from default snap store
            raw_response: httpx.Response = await self._client.request(
                "POST", f"{self.common_endpoint}/{snap}", json=request_data
            )
        response = AsyncResponse.model_validate_json(raw_response.content)
        if wait:
            changes_id = response.change
            previous_changes = None
            while True:
                try:
                    changes = await self._client.get_changes_by_id(changes_id)
                    logger.debug("Progress: %s", changes.result.overall_progress)
                except httpx.HTTPError:
                    if going_to_reload_daemon(previous_changes):
                        logger.debug("Waiting for daemon to reload")
                        changes = previous_changes

                if changes.ready:
                    break
                if changes.result.err:
                    raise SnapdAPIError(f"Error in snap install: {changes.result.err}")
                await asyncio.sleep(0.1)
                previous_changes = changes
            return changes
        return response

    async def remove_snap(
        self,
        snap: str,
        purge: bool = False,
        terminate: bool = False,
        wait: bool = False,
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
            changes_id = response.change
            previous_changes = None
            while True:
                try:
                    changes = await self._client.get_changes_by_id(changes_id)
                except httpx.HTTPError:
                    if going_to_reload_daemon(previous_changes):
                        logger.debug("Waiting for daemon to reload")
                        await asyncio.sleep(0.1)
                        continue
                if changes.ready:
                    break
                if changes.result.err:
                    raise SnapdAPIError(f"Error in snap remove: {changes.result.err}")
                await asyncio.sleep(0.1)
                previous_changes = changes
            return changes

        return response

    async def refresh_snap(
        self,
        snap: str,
        channel: str = "stable",
        classic: bool = False,
        dangerous: bool = False,
        devmode: bool = False,
        ignore_validation: bool = False,
        jailmode: bool = False,
        revision: int = None,
        filename: str = None,
        wait: bool = False,
    ) -> AsyncResponse | ChangesResponse:
        """
        Refreshes a snap package.

        :param snap: The name of the snap package to refresh.
        :type snap: str
        :param channel: The channel to refresh the snap from. Defaults to "stable".
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

        :returns: The response from the refresh operation.
        :rtype: AsyncResponse | ChangesResponse

        :raises FileNotFoundError: If the specified snap file does not exist.
        :raises ValueError: If attempting to sideload without the dangerous flag set to True.
        :raises SnapdAPIError: If there is an error during the snap refresh.
        """
        request_data = {
            "action": "refresh",
            "channel": channel,
            "classic": classic,
            "dangerous": dangerous,
            "devmode": devmode,
            "ignore_validation": ignore_validation,
            "jailmode": jailmode,
        }
        if revision:
            request_data["revision"] = revision
        if filename:
            # sideload
            if not Path(filename).exists():
                raise FileNotFoundError(f"File {filename} does not exist")
            if request_data.get("dangerous") is not True:
                raise ValueError(
                    "Cannot sideload snap without dangerous flag set to True"
                )
            raw_response: httpx.Response = await self._client.request(
                "POST",
                f"{self.common_endpoint}",
                data=request_data,
                files={"snap": open(filename, "rb")},
            )
        else:
            # install from default snap store
            raw_response: httpx.Response = await self._client.request(
                "POST", f"{self.common_endpoint}/{snap}", json=request_data
            )
        response = AsyncResponse.model_validate_json(raw_response.content)
        if wait:
            changes_id = response.change
            previous_changes = None
            while True:
                try:
                    changes = await self._client.get_changes_by_id(changes_id)
                    logger.debug("Progress: %s", changes.result.overall_progress)
                except httpx.HTTPError:
                    if going_to_reload_daemon(previous_changes):
                        logger.debug("Waiting for daemon to reload")
                        await asyncio.sleep(0.1)
                        continue

                if changes.ready:
                    break
                if changes.result.err:
                    raise SnapdAPIError(f"Error in snap remove: {changes.result.err}")
                await asyncio.sleep(0.1)
                previous_changes = changes
            return changes
        return response
