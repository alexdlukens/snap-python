from abc import ABC, abstractmethod

import httpx

from pysnap.schemas.changes import ChangesResponse


class AbstractSnapsClient(ABC):  # pragma: no cover
    @abstractmethod
    async def request(self) -> httpx.Response:
        pass

    @abstractmethod
    async def request_raw(self) -> httpx.Response:
        pass

    @abstractmethod
    async def get_changes_by_id(self, change_id: str) -> ChangesResponse:
        pass
