from typing import Any, Dict, List, Optional

from pydantic import AliasChoices, AwareDatetime, BaseModel, ConfigDict, Field

from snap_python.schemas.common import Revision
from snap_python.schemas.snaps import StoreSnap

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
    model_config = ConfigDict(extra="forbid", exclude_unset=True)

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
    model_config = ConfigDict(extra="forbid", exclude_unset=True, exclude_none=True)

    name: str
    revision: Optional[Revision] = None
    snap: StoreSnap
    snap_id: str = Field(alias=AliasChoices("snap-id", "snap_id"))


class SearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", exclude_unset=True, exclude_none=True)

    error_list: Optional[List[ErrorListItem]] = Field(None, alias="error-list")
    results: List[SearchResult]
