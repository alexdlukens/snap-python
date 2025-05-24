from typing import Optional

from pydantic import AliasChoices, AwareDatetime, BaseModel, ConfigDict, Field

from snap_python.schemas.common import (
    BaseErrorResult,
    BaseResponse,
    Media,
    Publisher,
    Revision,
    SnapApp,
)
from snap_python.schemas.store.categories import Category


class SnapHealth(BaseModel):
    status: str
    revision: str
    timestamp: AwareDatetime


class InstalledSnapFields(Revision):
    apps: list[SnapApp] = Field(default_factory=list)
    developer: Optional[str] = None
    devmode: Optional[bool] = None
    health: Optional[SnapHealth] = None
    icon: Optional[str] = None
    id: Optional[str] = Field(
        None, validation_alias=AliasChoices("id", "snap-id"), serialization_alias="id"
    )
    ignore_validation: bool = Field(
        validation_alias=AliasChoices("ignore-validation", "ignore_validation"),
        serialization_alias="ignore-validation",
    )
    install_date: Optional[AwareDatetime] = Field(
        default=None,
        validation_alias=AliasChoices("install-date", "install_date"),
        serialization_alias="install-date",
    )
    installed_size: int = Field(
        validation_alias=AliasChoices("installed-size", "installed_size"),
        serialization_alias="installed-size",
    )
    jailmode: bool
    mounted_from: str = Field(
        validation_alias=AliasChoices("mounted-from", "mounted_from"),
        serialization_alias="mounted-from",
    )
    status: str
    tracking_channel: Optional[str] = Field(
        validation_alias=AliasChoices("tracking-channel", "tracking_channel"),
        serialization_alias="tracking-channel",
        default=None,
    )


class StoreSnapFields(BaseModel):
    gated_snap_ids: Optional[list[str]] = Field(
        None, alias=AliasChoices("gated-snap-ids", "gated_snap_ids")
    )
    categories: Optional[list[Category]] = None
    prices: Optional[dict[str, str]] = None
    snap_id: Optional[str] = Field(None, alias=AliasChoices("snap-id", "snap_id"))
    store_url: Optional[str] = Field(None, alias=AliasChoices("store-url", "store_url"))
    trending: Optional[bool] = None


class Snap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contact: Optional[str] = None
    description: Optional[str] = None
    license: str = "unset"
    links: Optional[dict[str, list[str]]] = None
    media: Optional[list[Media]] = None
    name: Optional[str] = None
    private: Optional[bool] = None
    publisher: Optional[Publisher] = Field(None, description="The publisher.")
    summary: Optional[str] = None
    title: Optional[str] = None
    unlisted: Optional[bool] = None
    website: Optional[str] = None


class StoreSnap(Snap, StoreSnapFields):
    pass


class InstalledSnap(Snap, InstalledSnapFields):
    pass


class SingleInstalledSnapResponse(BaseResponse):
    result: InstalledSnap | BaseErrorResult


class InstalledSnapListResponse(BaseResponse):
    result: list[InstalledSnap]

    def __len__(self):
        return len(self.result)
