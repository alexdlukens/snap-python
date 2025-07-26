from typing import List, Optional

from pydantic import (
    AliasChoices,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
)

from snap_python.schemas.snaps import StoreSnap

VALID_SNAP_INFO_FIELDS = [
    "architectures",
    "base",
    "categories",
    "channel-map",
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
    "store-url",
    "summary",
    "title",
    "trending",
    "type",
    "unlisted",
    "version",
]


class Channel(BaseModel):
    model_config = ConfigDict(exclude_unset=True)

    architecture: str
    name: str
    released_at: Optional[AwareDatetime] = Field(
        None,
        alias=AliasChoices("released-at", "released_at"),
        serialization_alias="released-at",
    )
    risk: str
    track: str


class Delta(BaseModel):
    model_config = ConfigDict(exclude_unset=True)

    format: str
    sha3_384: Optional[str] = Field(
        None, alias=AliasChoices("sha3-384", "sha3_384"), serialization_alias="sha3-384"
    )
    size: float
    source: float
    target: float
    url: str


class Download(BaseModel):
    model_config = ConfigDict(exclude_unset=True)

    deltas: List[Delta]
    sha3_384: Optional[str] = Field(
        None, alias=AliasChoices("sha3-384", "sha3_384"), serialization_alias="sha3-384"
    )
    size: float
    url: str


class Epoch(BaseModel):
    model_config = ConfigDict(exclude_unset=True)

    read: List[float]
    write: List[float]


class Download1(BaseModel):
    sha3_384: Optional[str] = Field(
        None, alias=AliasChoices("sha3-384", "sha3_384"), serialization_alias="sha3-384"
    )
    size: Optional[int] = None
    url: Optional[str] = None


class Resource(BaseModel):
    model_config = ConfigDict(exclude_unset=True)

    architectures: Optional[List[str]] = None
    created_at: Optional[str] = Field(
        None,
        alias=AliasChoices("created-at", "created_at"),
        serialization_alias="created-at",
    )
    description: Optional[str] = None
    download: Optional[Download1] = None
    name: Optional[str] = None
    revision: Optional[int] = None
    type: Optional[str] = None
    version: Optional[str] = None


class ChannelMapItem(BaseModel):
    model_config = ConfigDict(exclude_unset=True)

    architectures: Optional[List[str]] = None
    base: Optional[str] = None
    channel: Channel
    common_ids: Optional[List[str]] = Field(
        None,
        alias=AliasChoices("common-ids", "common_ids"),
        serialization_alias="common-ids",
    )
    confinement: Optional[str] = None
    created_at: Optional[AwareDatetime] = Field(
        None,
        alias=AliasChoices("created-at", "created_at"),
        serialization_alias="created-at",
    )
    download: Optional[Download] = None
    epoch: Optional[Epoch] = None
    resources: Optional[List[Resource]] = None
    revision: Optional[int] = None
    snap_yaml: Optional[str] = Field(
        None,
        alias=AliasChoices("snap-yaml", "snap_yaml"),
        serialization_alias="snap-yaml",
    )
    type: Optional[str] = None
    version: Optional[str] = None


class ErrorListItem(BaseModel):
    model_config = ConfigDict(exclude_unset=True)

    code: str
    message: str


class InfoResponse(BaseModel):
    model_config = ConfigDict(exclude_unset=True)

    channel_map: List[ChannelMapItem] = Field(
        ...,
        alias=AliasChoices("channel-map", "channel_map"),
        serialization_alias="channel-map",
    )
    default_track: Optional[str] = Field(
        None,
        alias=AliasChoices("default-track", "default_track"),
        serialization_alias="default-track",
    )
    error_list: Optional[List[ErrorListItem]] = Field(
        None,
        alias=AliasChoices("error-list", "error_list"),
        serialization_alias="error-list",
    )
    name: str
    snap: StoreSnap
    snap_id: str = Field(
        ..., alias=AliasChoices("snap-id", "snap_id"), serialization_alias="snap-id"
    )
