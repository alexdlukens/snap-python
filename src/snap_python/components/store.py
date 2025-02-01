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
    ArchSearchResponse,
    SearchResponse,
)
from snap_python.schemas.store.utils import VALID_SNAP_ARCHITECTURES


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
        """
        Get details of a snap.

        :param snap_name: The name of the snap.
        :type snap_name: str
        :param fields: The fields to include in the response.
        :type fields: list[str], optional

        :returns: The snap details.
        :rtype: dict

        :raises ValueError: If invalid fields are provided.
        """
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

    async def get_snap_info(
        self, snap_name: str, fields: list[str] | None = None
    ) -> InfoResponse:
        """
        Get information about a snap.

        :param snap_name: The name of the snap.
        :type snap_name: str
        :param fields: The fields to include in the response.
        :type fields: list[str], optional

        :returns: The snap information.
        :rtype: InfoResponse

        :raises ValueError: If invalid fields are provided.
        """
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
        """
        Get categories of snaps.

        :param type: The type of categories.
        :type type: str, optional
        :param fields: The fields to include in the response.
        :type fields: list[str], optional

        :returns: The categories.
        :rtype: CategoryResponse

        :raises ValueError: If invalid fields are provided.
        """
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
        """
        Get a category by name.

        :param name: The name of the category.
        :type name: str
        :param fields: The fields to include in the response.
        :type fields: list[str], optional

        :returns: The category.
        :rtype: SingleCategoryResponse

        :raises ValueError: If invalid fields are provided.
        """
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
        """
        Search for snaps in the store.

        :param query: The search query.
        :type query: str, optional
        :param fields: The fields to include in the response.
        :type fields: str, optional
        :param name_startswith: Filter snaps by name prefix.
        :type name_startswith: str, optional
        :param architecture: Filter snaps by architecture.
        :type architecture: str, optional
        :param common_id: Filter snaps by common ID.
        :type common_id: str, optional
        :param category: Filter snaps by category.
        :type category: str, optional
        :param channel: Filter snaps by channel.
        :type channel: str, optional
        :param confiement: Filter snaps by confinement.
        :type confiement: str, optional
        :param featured: Filter snaps by featured status.
        :type featured: bool, optional
        :param private: Filter snaps by private status.
        :type private: bool, optional
        :param publisher: Filter snaps by publisher.
        :type publisher: str, optional
        :param headers: Additional headers to include in the request.
        :type headers: dict[str, str], optional

        :returns: The search response.
        :rtype: SearchResponse

        :raises ValueError: If invalid fields are provided.
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
        """
        Retry getting snap information.

        :param snap_name: The name of the snap.
        :type snap_name: str
        :param fields: The fields to include in the response.
        :type fields: list[str]

        :returns: The snap information.
        :rtype: InfoResponse
        """
        return await self.get_snap_info(snap_name=snap_name, fields=fields)

    async def get_top_snaps_from_category(self, category: str) -> SearchResponse:
        """
        Get top snaps from a category.

        :param category: The category name.
        :type category: str

        :returns: The search response.
        :rtype: SearchResponse
        """
        return await self.find(
            category=category, fields=["title", "store-url", "summary"]
        )

    async def get_all_snaps_for_arch(self, arch: str) -> ArchSearchResponse:
        """
        Get all snaps for a given architecture.

        :param arch: The architecture.
        :type arch: str

        :returns: The search response.
        :rtype: ArchSearchResponse

        :raises ValueError: If invalid architecture is provided.
        """
        # use the old "/api/v1/snaps/names" to get all snaps for a given architecture

        # ensure valid arch
        if arch not in VALID_SNAP_ARCHITECTURES:
            raise ValueError(f"Invalid architecture: {arch}")

        route = "/api/v1/snaps/names"
        extra_headers = {"X-Ubuntu-Architecture": arch}

        response = await self.store_client.get(
            f"{self._raw_base_url}{route}", headers=extra_headers, timeout=60
        )
        response.raise_for_status()

        response_json = response.json()
        response_json["arch"] = arch
        return ArchSearchResponse.model_validate(response_json)
