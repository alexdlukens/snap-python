import functools

import retry
from httpx import AsyncClient

from snap_python.schemas.store.categories import (
    VALID_CATEGORY_FIELDS,
    CategoryResponse,
    SingleCategoryResponse,
)
from snap_python.schemas.store.info import VALID_SNAP_INFO_FIELDS, InfoResponse
from snap_python.schemas.store.search import (
    VALID_SEARCH_CATEGORY_FIELDS,
    SearchResponse,
)


class StoreEndpoints:
    """Query snap store that is available at <base_url> for information about snaps.
    Calls made directly with store to enable querying the non-default snap store for information.
    Snapd only supports the store at snapcraft.io

    Certain functionality is not available in snapd, such as querying for/by categories
    """

    def __init__(
        self, base_url: str, version: str, headers: dict[str, str] = None
    ) -> None:
        self.store_client = AsyncClient()
        self.store_client.request = functools.partial(
            self.store_client.request, timeout=5
        )
        self.base_url = f"{base_url}/{version}"
        self._raw_base_url = base_url
        if headers is not None:
            self.store_client.headers.update(headers)

    async def get_snap_details(self, snap_name: str, fields: list[str] | None = None):
        query = {}
        if fields is not None:
            if not all(field in VALID_SEARCH_CATEGORY_FIELDS for field in fields):
                raise ValueError(
                    f"Invalid fields. Allowed fields: {VALID_SEARCH_CATEGORY_FIELDS}"
                )
            query["fields"] = ",".join(fields)
        route = f"/api/v1/snaps/details/{snap_name}"
        response = await self.store_client.get(
            f"{self._raw_base_url}{route}", params=query
        )
        response.raise_for_status()
        return response.json()

    async def get_snap_info(self, snap_name: str, fields: list[str] | None = None):
        query = {}
        if fields is not None:
            if not all(field in VALID_SNAP_INFO_FIELDS for field in fields):
                raise ValueError(
                    f"Invalid fields. Allowed fields: {VALID_SNAP_INFO_FIELDS}"
                )
            query["fields"] = ",".join(fields)
        route = f"/v2/snaps/info/{snap_name}"
        response = await self.store_client.get(
            f"{self._raw_base_url}{route}", params=query
        )
        response.raise_for_status()
        return InfoResponse.model_validate_json(response.content)

    async def get_categories(
        self, type: str | None = None, fields: list[str] | None = None
    ) -> CategoryResponse:
        query = {}
        if fields is not None:
            if not all(field in VALID_CATEGORY_FIELDS for field in fields):
                raise ValueError(
                    f"Invalid fields. Allowed fields: {VALID_CATEGORY_FIELDS}"
                )
            query["fields"] = ",".join(fields)
        if type is not None:
            query["type"] = type
        route = "/snaps/categories"
        response = await self.store_client.get(f"{self.base_url}{route}", params=query)
        response.raise_for_status()
        return CategoryResponse.model_validate_json(response.content)

    async def get_category_by_name(
        self, name: str, fields: list[str] | None = None
    ) -> SingleCategoryResponse:
        query = {}
        if fields is not None:
            if not all(field in VALID_CATEGORY_FIELDS for field in fields):
                raise ValueError(
                    f"Invalid fields. Allowed fields: {VALID_CATEGORY_FIELDS}"
                )
            query["fields"] = ",".join(fields)

        route = f"/snaps/category/{name}"
        response = await self.store_client.get(f"{self.base_url}{route}", params=query)
        response.raise_for_status()
        return SingleCategoryResponse.model_validate_json(response.content)

    async def find(
        self,
        query: str | None = None,
        fields: str | None = None,
        name_startswith: str | None = None,
        architecture: str | None = None,
        common_id: str | None = None,
        category: str | None = None,
        channel: str | None = None,
        confiement: str | None = None,
        featured: bool = False,
        private: bool = False,
        publisher: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> SearchResponse:
        """from https://api.snapcraft.io/docs/search.html#snaps_find
        and https://snapcraft.io/docs/snapd-api#heading--find
        """

        route = "/snaps/find"
        query_dict: dict = {
            "q": query,
            "name_startswith": name_startswith,
            "architecture": architecture,
            "common_id": common_id,
            "category": category,
            "channel": channel,
            "confinement": confiement,
            "featured": featured,
            "private": private,
            "publisher": publisher,
        }
        if fields is not None:
            if not all(field in VALID_SEARCH_CATEGORY_FIELDS for field in fields):
                bad_fields = [
                    field
                    for field in fields
                    if field not in VALID_SEARCH_CATEGORY_FIELDS
                ]
                raise ValueError(
                    f"Invalid fields: ({bad_fields}). Allowed fields: {VALID_SEARCH_CATEGORY_FIELDS}"
                )
            query_dict["fields"] = ",".join(fields)
        extra_headers = headers or {}
        query_dict = {
            k: v for k, v in query_dict.items() if (v is not None) and (v != "")
        }

        # snap store expects "true" or "false" for boolean values
        for key in ["featured", "private"]:
            if key in query_dict:
                query_dict[key] = str(query_dict[key]).lower()

        response = await self.store_client.get(
            f"{self.base_url}{route}", params=query_dict, headers=extra_headers
        )
        response.raise_for_status()
        return SearchResponse.model_validate_json(response.content)

    @retry.retry(Exception, tries=3, delay=2, backoff=2)
    async def retry_get_snap_info(self, snap_name: str, fields: list[str]):
        return await self.get_snap_info(snap_name=snap_name, fields=fields)

    async def get_top_snaps_from_category(self, category: str) -> SearchResponse:
        return await self.find(
            category=category, fields=["title", "store-url", "summary"]
        )
