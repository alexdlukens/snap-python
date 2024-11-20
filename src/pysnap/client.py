import httpx

SNAPD_SOCKET = "/run/snapd.socket"


class SnapClient:
    def __init__(self, version: str = "v2"):
        self.version = version
        self._base_url = "http://localhost"
        self._transport = httpx.AsyncHTTPTransport(uds=SNAPD_SOCKET)
        self.client = httpx.AsyncClient(transport=self._transport)

    async def ping(self) -> httpx.Response:
        """Reserved for human-readable content describing the service.

        Returns:
            httpx.Response: _description_
        """
        response = await self.client.get(f"{self._base_url}/")

        return response
