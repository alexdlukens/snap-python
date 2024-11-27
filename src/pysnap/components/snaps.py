import httpx

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
    ) -> httpx.Response:
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
        response: httpx.Response = await self._client.request(
            "POST", f"{self.common_endpoint}/{snap}", json=request_data
        )
        return response

    async def remove_snap(
        self, snap: str, purge: bool, terminate: bool
    ) -> httpx.Response:
        request_data = {
            "action": "remove",
            "purge": purge,
            "terminate": terminate,
        }

        response: httpx.Response = await self._client.request(
            "POST", f"{self.common_endpoint}/{snap}", json=request_data
        )
        return response
