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
