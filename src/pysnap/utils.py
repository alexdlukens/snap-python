from abc import ABC, abstractmethod

import httpx


class AbstractSnapsClient(ABC):
    @abstractmethod
    async def request(self) -> httpx.Response:
        pass

    @abstractmethod
    async def request_raw(self) -> httpx.Response:
        pass
