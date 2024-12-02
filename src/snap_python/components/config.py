import asyncio
import logging

import httpx

from snap_python.schemas.changes import ChangesResponse
from snap_python.schemas.common import AsyncResponse
from snap_python.schemas.config import ConfigResponse
from snap_python.utils import AbstractSnapsClient

logger = logging.getLogger("snap_python.components.snaps")


class ConfigEndpoints:
    def __init__(self, client: AbstractSnapsClient) -> None:
        self._client = client
        self.common_endpoint = "snaps"

    async def get_configuration(
        self, snap: str, keys: list[str] | None = None
    ) -> ConfigResponse:
        if keys:
            response: httpx.Response = await self._client.request(
                "GET",
                f"{self.common_endpoint}/{snap}/conf",
                params={"keys": ",".join(keys)},
            )
        else:
            response: httpx.Response = await self._client.request(
                "GET", f"{self.common_endpoint}/{snap}/conf"
            )

        return ConfigResponse.model_validate_json(response.content)

    async def set_configuration(
        self, snap: str, configuration: dict, wait: bool = True
    ) -> AsyncResponse | ChangesResponse:
        # TODO: should check that snap supports configure hook before trying to set configuration
        response: httpx.Response = await self._client.request(
            "PUT", f"{self.common_endpoint}/{snap}/conf", json=configuration
        )

        async_response = AsyncResponse.model_validate_json(response.content)
        if not wait:
            return async_response
        while True:
            changes = await self._client.get_changes_by_id(async_response.change)

            if changes.ready:
                break

            await asyncio.sleep(0.1)

        return changes
