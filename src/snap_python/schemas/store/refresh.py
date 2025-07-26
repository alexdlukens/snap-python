from typing import List, Optional

from pydantic import AliasChoices, AwareDatetime, BaseModel, ConfigDict, Field

from snap_python.schemas.snaps import Snap
from snap_python.schemas.store.info import Download, ErrorListItem, Resource

VALID_SNAP_REFRESH_FIELDS = [
    "architectures",
    "base",
    "common-ids",
    "confinement",
    "contact",
    "created-at",
    "description",
    "download",
    "epoch",
    "gated-snap-ids",
    "license",
    "links",
    "media",
    "name",
    "prices",
    "private",
    "publisher",
    "resources",
    "revision",
    "snap-id",
    "snap-yaml",
    "summary",
    "title",
    "type",
    "version",
    "website",
]


class SnapRefreshFields(BaseModel):
    architectures: Optional[list[str]] = None
    base: Optional[str] = None
    common_ids: Optional[list[str]] = Field(
        None, alias=AliasChoices("common-ids", "common_ids")
    )
    confinement: Optional[str] = None
    created_at: Optional[AwareDatetime] = Field(
        None,
        alias=AliasChoices("created-at", "created_at"),
        serialization_alias="created-at",
    )
    download: Optional[Download] = None
    epoch: Optional[dict[str, list[int]]] = None
    gated_snap_ids: Optional[list[str]] = Field(
        None, alias=AliasChoices("gated-snap-ids", "gated_snap_ids")
    )
    license: Optional[str] = None
    prices: Optional[dict[str, str]] = None
    resources: list[Resource] = Field(default_factory=list)
    revision: Optional[int] = None
    snap_id: Optional[str] = Field(
        None, alias=AliasChoices("snap-id", "snap_id"), serialization_alias="snap-id"
    )
    snap_yaml: Optional[str] = Field(
        None,
        alias=AliasChoices("snap-yaml", "snap_yaml"),
        serialization_alias="snap-yaml",
    )
    type: Optional[str] = None
    version: Optional[str] = None


class StoreRefreshSnap(Snap, SnapRefreshFields):
    pass


class RefreshResultError(BaseModel):
    code: str
    message: str
    extra: Optional[dict] = None


class RefreshResultData(BaseModel):
    model_config = ConfigDict(exclude_unset=True)

    default_track: Optional[str] = Field(
        None,
        alias=AliasChoices("default-track", "default_track"),
        serialization_alias="default-track",
    )

    name: str
    snap: StoreRefreshSnap
    instance_key: str = Field(
        ...,
        alias=AliasChoices("instance-key", "instance_key"),
        serialization_alias="instance-key",
    )
    released_at: Optional[AwareDatetime] = Field(
        None,
        alias=AliasChoices("released-at", "released_at"),
        serialization_alias="released-at",
    )
    result: str

    snap_id: str = Field(
        ..., alias=AliasChoices("snap-id", "snap_id"), serialization_alias="snap-id"
    )
    error: RefreshResultError | None = None

    @property
    def is_error(self) -> bool:
        if self.error:
            return True
        return False


class RefreshRevisionResponse(BaseModel):
    error_list: Optional[List[ErrorListItem]] = Field(
        None,
        alias=AliasChoices("error-list", "error_list"),
        serialization_alias="error-list",
    )
    results: List[RefreshResultData]
