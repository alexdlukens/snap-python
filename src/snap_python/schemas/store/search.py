from typing import Any, Dict, List, Optional

from pydantic import AliasChoices, AwareDatetime, BaseModel, ConfigDict, Field

from snap_python.schemas.common import Revision
from snap_python.schemas.snaps import InstalledSnap, StoreSnap, StoreSnapFields

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
    model_config = ConfigDict(extra="forbid")

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
        snap_name = snap_info.pop("name")

        # get set of acceptable fields for StoreSnap
        store_snap_fields = StoreSnapFields.model_fields.keys()
        snap_info = {
            key: value for key, value in snap_info.items() if key in store_snap_fields
        }

        snap_info = {"snap": snap_info, "snap-id": snap_id, "name": snap_name}
        snap_info["revision"] = revision_info

        return cls.model_validate(snap_info)


class SearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error_list: Optional[List[ErrorListItem]] = Field(None, alias="error-list")
    results: List[SearchResult]
