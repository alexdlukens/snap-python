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
        """Install or sideload a snap

        To sideload a snap, provide the filename parameter with the path to the snap file


        Args:
            snap (str): name of the snap to install
            channel (str, optional): Channel to install. Defaults to "stable".
            classic (bool, optional): Install with classic confinement. Defaults to False.
            dangerous (bool, optional): install the given snap files even if there are no pre-acknowledged signatures for them, meaning they are not verified and could be dangerous if true (optional, implied by devmode). Defaults to False.
            devmode (bool, optional): Install with devmode. Defaults to False.
            jailmode (bool, optional): Install snap with jailmode. Defaults to False.
            revision (int, optional): install a specific revision of the snap. Defaults to None.
            filename (str, optional): Path to snap to sideload. Defaults to None.
            wait (bool, optional): Whether to wait for snap to install. If not waiting, will return async response with change id. Defaults to False.

        Raises:
            SnapdAPIError: If error occurs during snap install

        Returns:
            AsyncResponse | ChangesResponse: If wait is True, will return ChangesResponse. Otherwise, will return AsyncResponse
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
        Args:
            snap (str): The name of the snap package to remove.
            purge (bool, optional): If True, purges the snap package. Defaults to False.
            terminate (bool, optional): If True, terminates the snap package. Defaults to False.
            wait (bool, optional): If True, waits for the removal process to complete. Defaults to False.
        Returns:
            AsyncResponse | ChangesResponse: The response from the snapd API, either an asynchronous response or a changes response if waiting for completion.
        Raises:
            SnapdAPIError: If there is an error in the snap removal process.
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
        Args:
            snap (str): The name of the snap package to refresh.
            channel (str, optional): The channel to refresh the snap from. Defaults to "stable".
            classic (bool, optional): Whether to use classic confinement. Defaults to False.
            dangerous (bool, optional): Whether to allow installation of unasserted snaps. Defaults to False.
            devmode (bool, optional): Whether to use development mode. Defaults to False.
            ignore_validation (bool, optional): Whether to ignore validation. Defaults to False.
            jailmode (bool, optional): Whether to use jail mode. Defaults to False.
            revision (int, optional): The specific revision to refresh to. Defaults to None.
            filename (str, optional): The path to the snap file for sideloading. Defaults to None.
            wait (bool, optional): Whether to wait for the refresh operation to complete. Defaults to False.
        Returns:
            AsyncResponse | ChangesResponse: The response from the refresh operation.
        Raises:
            FileNotFoundError: If the specified snap file does not exist.
            ValueError: If attempting to sideload without the dangerous flag set to True.
            SnapdAPIError: If there is an error during the snap refresh.
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
