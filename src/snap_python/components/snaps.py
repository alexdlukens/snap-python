import asyncio
import logging
from pathlib import Path

import httpx

from snap_python.schemas.changes import ChangesResponse
from snap_python.schemas.common import AsyncResponse
from snap_python.schemas.snaps import SingleSnapResponse, SnapListResponse
from snap_python.utils import AbstractSnapsClient, going_to_reload_daemon

logger = logging.getLogger("snap_python.components.snaps")


class SnapsEndpoints:
    def __init__(self, client: AbstractSnapsClient) -> None:
        self._client = client
        self.common_endpoint = "snaps"

    async def list_installed_snaps(self) -> SnapListResponse:
        response: httpx.Response = await self._client.request(
            "GET", self.common_endpoint
        )

        response = SnapListResponse.model_validate_json(response.content)
        if response.status_code > 299:
            raise httpx.HTTPStatusError(
                request=response.request,
                response=response,
                message=f"Invalid status code in response: {response.status_code}",
            )
        return response

    async def get_snap_info(self, snap: str) -> SingleSnapResponse:
        response: httpx.Response = await self._client.request(
            "GET", f"{self.common_endpoint}/{snap}"
        )

        return SingleSnapResponse.model_validate_json(response.content)

    async def install_snap(
        self,
        snap: str,
        channel: str = "stable",
        classic: bool = False,
        devmode: bool = False,
        ignore_validation: bool = False,
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
            devmode (bool, optional): Install with devmode. Defaults to False.
            ignore_validation (bool, optional): _description_. Defaults to False.
            jailmode (bool, optional): Install snap with jailmode. Defaults to False.
            revision (int, optional): install a specific revision of the snap. Defaults to None.
            filename (str, optional): Path to snap to sideload. Defaults to None.
            wait (bool, optional): Whether to wait for snap to install. If not waiting, will return async response with change id. Defaults to False.

        Raises:
            Exception: If error occurs during snap install

        Returns:
            AsyncResponse | ChangesResponse: If wait is True, will return ChangesResponse. Otherwise, will return AsyncResponse
        """
        request_data = {
            "action": "install",
            "channel": channel,
            "classic": classic,
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
            request_data["dangerous"] = True
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
                    logger.debug(f"Progress: {changes.result.overall_progress}")
                except httpx.HTTPError as e:
                    if going_to_reload_daemon(previous_changes):
                        logger.debug("Waiting for daemon to reload")
                        await asyncio.sleep(0.1)
                        continue

                if changes.ready:
                    break
                if changes.result.err:
                    raise Exception(f"Error in snap install: {changes.result.err}")
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
                except httpx.HTTPError as e:
                    if going_to_reload_daemon(previous_changes):
                        logger.debug("Waiting for daemon to reload")
                        await asyncio.sleep(0.1)
                        continue
                if changes.ready:
                    break
                if changes.result.err:
                    raise Exception(f"Error in snap remove: {changes.result.err}")
                await asyncio.sleep(0.1)
                previous_changes = changes
            return changes

        return response
