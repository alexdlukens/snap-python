from enum import Enum
from typing import Literal, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class BaseResponse(BaseModel):
    status_code: int = Field(
        validation_alias=AliasChoices("status-code", "status_code"),
        serialization_alias="status-code",
    )
    type: Literal["sync", "async"]
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
    model_config = ConfigDict(extra="forbid", exclude_unset=True)

    height: Optional[float] = None
    type: str
    url: str
    width: Optional[float] = None


class AsyncResponse(BaseResponse):
    change: str
