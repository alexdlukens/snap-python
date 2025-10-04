from enum import Enum
from typing import Literal, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

VALID_SNAP_ARCHITECTURES = [
    "amd64",
    "arm64",
    "armhf",
    "i386",
    "powerpc",
    "ppc64el",
    "riscv64",
    "s390x",
]


class BaseErrorResult(BaseModel):
    message: str


class BaseResponse(BaseModel):
    status_code: int = Field(
        validation_alias=AliasChoices("status-code", "status_code"),
        serialization_alias="status-code",
    )
    type: Literal["sync", "async", "error"]
    status: str


class SnapBaseVersion(Enum):
    core16 = "core16"
    core18 = "core18"
    core20 = "core20"
    core22 = "core22"
    core24 = "core24"
    bare = "bare"


class SnapConfinement(Enum):
    strict = "strict"
    classic = "classic"
    devmode = "devmode"
    jailmode = "jailmode"


class SnapApp(BaseModel):
    snap: str | None = None
    name: str
    desktop_file: str | None = Field(
        default=None,
        validation_alias=AliasChoices("desktop-file", "desktop_file"),
        serialization_alias="desktop-file",
    )
    daemon: str | None = None
    enabled: bool | None = None
    active: bool | None = None
    common_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("common-id", "common_id"),
        serialization_alias="common-id",
    )


class Media(BaseModel):
    model_config = ConfigDict(exclude_unset=True)

    height: Optional[float] = None
    type: str
    url: str
    width: Optional[float] = None


class AsyncResponse(BaseResponse):
    change: str


class Download(BaseModel):
    model_config = ConfigDict(exclude_unset=True)

    size: float


class Revision(BaseModel):
    model_config = ConfigDict(exclude_unset=True)

    base: Optional[SnapBaseVersion] = None
    channel: Optional[str] = None
    common_ids: Optional[list[str]] = Field(
        None, validation_alias=AliasChoices("common-ids", "common_ids")
    )
    confinement: Optional[SnapConfinement] = None
    download: Optional[Download] = None
    revision: Optional[int | str] = None
    type: Optional[str] = None
    version: Optional[str] = None


class Publisher(BaseModel):
    model_config = ConfigDict(exclude_unset=True)

    display_name: str = Field(
        ...,
        validation_alias=AliasChoices("display-name", "display_name"),
        description="Display name corresponding to the publisher.",
    )
    id: str = Field(..., description="The publisher id.")
    username: str = Field(..., description="Username belonging to the publisher.")
    validation: Optional[str] = Field(
        None, description="Indicates if the account has been validated."
    )
