import asyncio

import httpx

from pysnap.schemas.changes import ChangesResponse
from pysnap.schemas.common import AsyncResponse
from pysnap.schemas.snaps import SnapListResponse
from pysnap.utils import AbstractSnapsClient


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

    async def install_snap(
        self,
        snap: str,
        channel: str = "stable",
        classic: bool = False,
        devmode: bool = False,
        ignore_validation: bool = False,
        jailmode: bool = False,
        revision: int = None,
        wait: bool = False,
    ) -> AsyncResponse | ChangesResponse:
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
        raw_response: httpx.Response = await self._client.request(
            "POST", f"{self.common_endpoint}/{snap}", json=request_data
        )
        response = AsyncResponse.model_validate_json(raw_response.content)
        if wait:
            changes_id = response.change
            while True:
                changes = await self._client.get_changes_by_id(changes_id)
                if changes.ready:
                    break
                if changes.result.err:
                    raise Exception(f"Error in snap install: {changes.result.err}")
                await asyncio.sleep(2.0)
            return changes
        return response

    async def remove_snap(
        self, snap: str, purge: bool, terminate: bool, wait: bool = False
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
            while True:
                changes = await self._client.get_changes_by_id(changes_id)
                if changes.ready:
                    break
                if changes.result.err:
                    raise Exception(f"Error in snap remove: {changes.result.err}")
                await asyncio.sleep(2.0)
            return changes

        return response
