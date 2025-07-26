from typing import Any, Dict, List, Optional

from pydantic import (
    AliasChoices,
    AliasPath,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
)

from snap_python.schemas.common import Revision
from snap_python.schemas.snaps import InstalledSnap, Snap, StoreSnap, StoreSnapFields

VALID_SEARCH_CATEGORY_FIELDS = [
    "base",
    "categories",
    "channel",
    "common-ids",
    "confinement",
    "contact",
    "description",
    "download",
    "license",
    "media",
    "prices",
    "private",
    "publisher",
    "revision",
    "store-url",
    "summary",
    "title",
    "type",
    "version",
    "website",
]


class ErrorListItem(BaseModel):
    model_config = ConfigDict(exclude_unset=True)

    code: str
    message: str


class SnapDetails(BaseModel):
    aliases: Optional[List[Dict]] = None
    anon_download_url: str
    apps: Optional[List[str]] = None
    architecture: List[str]
    base: Optional[str] = None
    binary_filesize: int
    channel: str
    common_ids: List[str]
    confinement: str
    contact: Optional[str] = None
    content: Optional[str] = None
    date_published: AwareDatetime
    deltas: Optional[List[str]] = None
    description: str
    developer_id: str
    developer_name: str
    developer_validation: str
    download_sha3_384: Optional[str] = None
    download_sha512: Optional[str] = None
    download_url: str
    epoch: str
    gated_snap_ids: Optional[List[str]] = None
    icon_url: str
    last_updated: AwareDatetime
    license: str
    links: Dict[str, Any]
    name: str
    origin: str
    package_name: str
    prices: Dict[str, Any]
    private: bool
    publisher: str
    raitings_average: float = 0.0
    release: List[str]
    revision: int
    screenshot_urls: List[str]
    snap_id: Optional[str] = None
    summary: Optional[str] = None
    support_url: Optional[str] = None
    title: Optional[str] = None
    version: Optional[str] = None
    website: Optional[str] = None


class SearchResult(BaseModel):
    name: str
    revision: Optional[Revision] = None
    snap: StoreSnap
    snap_id: str = Field(alias=AliasChoices("snap-id", "snap_id"))

    @classmethod
    def from_installed_snap(cls, installed_snap: InstalledSnap):
        snap_info: dict = installed_snap.model_dump(mode="json")
        revision_snap_fields = Revision.model_fields.keys()
        revision_info = {}
        for field in revision_snap_fields:
            if field in snap_info:
                revision_info[field] = snap_info.pop(field)

        snap_id = snap_info.pop("id")
        snap_name = snap_info.get("name")

        # get set of acceptable fields for StoreSnap
        store_snap_fields = set(StoreSnapFields.model_fields.keys()).union(
            Snap.model_fields.keys()
        )
        store_snap_info = {
            key: value for key, value in snap_info.items() if key in store_snap_fields
        }

        snap_info = {"snap": store_snap_info, "snap-id": snap_id, "name": snap_name}
        snap_info["revision"] = revision_info

        return cls.model_validate(snap_info)


class SearchResponse(BaseModel):
    error_list: Optional[List[ErrorListItem]] = Field(None, alias="error-list")
    results: List[SearchResult]


class ArchSearchItem(BaseModel):
    aliases: Optional[list[dict[str, str]]]
    apps: list[str]
    package_name: str
    summary: str
    title: str
    version: str


class ArchSearchResponse(BaseModel):
    results: list[ArchSearchItem] = Field(
        alias=AliasChoices(AliasPath("_embedded", "clickindex:package"), "results")
    )
    arch: str = "wide"


class PaginatedResponse(BaseModel):
    total: int
    page: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)

    @computed_field
    @property
    def next_page(self) -> Optional[int]:
        if self.page * self.limit + self.limit < self.total:
            return self.page + 1
        return None

    @computed_field
    @property
    def previous_page(self) -> Optional[int]:
        if self.page > 0:
            return self.page - 1
        return None

    @computed_field
    @property
    def has_more(self) -> bool:
        return self.page * self.limit + self.limit < self.total


class PaginatedSnapSearchResponse(PaginatedResponse):
    results: list[ArchSearchItem] = Field(
        alias=AliasChoices(AliasPath("_embedded", "clickindex:package"), "results")
    )
