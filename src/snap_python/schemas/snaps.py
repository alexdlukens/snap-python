from typing import Optional

from pydantic import (
    AliasChoices,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
)

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


class SnapRefreshInhibit(BaseModel):
    """A pending refresh for a running snap."""

    proceed_time: AwareDatetime = Field(
        validation_alias=AliasChoices("proceed-time", "proceed_time"),
        serialization_alias="proceed-time",
    )


class SnapRefreshFailures(BaseModel):
    """Information about failed refresh attempts for a snap."""

    revision: Optional[int | str] = None
    failure_count: int = Field(
        validation_alias=AliasChoices("failure-count", "failure_count"),
        serialization_alias="failure-count",
    )
    last_failure_time: AwareDatetime = Field(
        validation_alias=AliasChoices("last-failure-time", "last_failure_time"),
        serialization_alias="last-failure-time",
    )
    last_failure_severity: Optional[str] = Field(
        None,
        validation_alias=AliasChoices("last-failure-severity", "last_failure_severity"),
        serialization_alias="last-failure-severity",
    )


class SnapComponent(BaseModel):
    """A component shipped with an installed snap."""

    model_config = ConfigDict(exclude_unset=True)

    name: str
    type: Optional[str] = None
    version: Optional[str] = None
    summary: Optional[str] = None
    description: Optional[str] = None
    revision: Optional[int | str] = None
    installed_size: Optional[int] = Field(
        None,
        validation_alias=AliasChoices("installed-size", "installed_size"),
        serialization_alias="installed-size",
    )
    install_date: Optional[AwareDatetime] = Field(
        None,
        validation_alias=AliasChoices("install-date", "install_date"),
        serialization_alias="install-date",
    )


class ChannelSnapInfo(BaseModel):
    """A flattened ``track/risk`` entry from a snap's channel map."""

    model_config = ConfigDict(exclude_unset=True)

    revision: Optional[int | str] = None
    confinement: Optional[str] = None
    version: Optional[str] = None
    channel: Optional[str] = None
    epoch: Optional[dict] = None
    size: Optional[int] = None
    released_at: Optional[AwareDatetime] = Field(
        None,
        validation_alias=AliasChoices("released-at", "released_at"),
        serialization_alias="released-at",
    )


class InstalledSnapFields(Revision):
    apps: list[SnapApp] = Field(default_factory=list)
    broken: Optional[str] = None
    channels: Optional[dict[str, ChannelSnapInfo]] = None
    cohort_key: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("cohort-key", "cohort_key"),
        serialization_alias="cohort-key",
    )
    components: list[SnapComponent] = Field(default_factory=list)
    developer: Optional[str] = None
    devmode: Optional[bool] = None
    gating_hold: Optional[AwareDatetime] = Field(
        default=None,
        validation_alias=AliasChoices("gating-hold", "gating_hold"),
        serialization_alias="gating-hold",
    )
    grade: Optional[str] = None
    health: Optional[SnapHealth] = None
    hold: Optional[AwareDatetime] = None
    icon: Optional[str] = None
    id: Optional[str] = Field(
        None, validation_alias=AliasChoices("id", "snap-id"), serialization_alias="id"
    )
    ignore_validation: bool = Field(
        default=False,
        validation_alias=AliasChoices("ignore-validation", "ignore_validation"),
        serialization_alias="ignore-validation",
    )
    install_date: Optional[AwareDatetime] = Field(
        default=None,
        validation_alias=AliasChoices("install-date", "install_date"),
        serialization_alias="install-date",
    )
    installed_size: Optional[int] = Field(
        default=None,
        validation_alias=AliasChoices("installed-size", "installed_size"),
        serialization_alias="installed-size",
    )
    jailmode: bool = False
    mounted_from: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("mounted-from", "mounted_from"),
        serialization_alias="mounted-from",
    )
    refresh_failures: Optional[SnapRefreshFailures] = Field(
        default=None,
        validation_alias=AliasChoices("refresh-failures", "refresh_failures"),
        serialization_alias="refresh-failures",
    )
    refresh_inhibit: Optional[SnapRefreshInhibit] = Field(
        default=None,
        validation_alias=AliasChoices("refresh-inhibit", "refresh_inhibit"),
        serialization_alias="refresh-inhibit",
    )
    status: Optional[str] = None
    tracking_channel: Optional[str] = Field(
        validation_alias=AliasChoices("tracking-channel", "tracking_channel"),
        serialization_alias="tracking-channel",
        default=None,
    )
    tracks: list[str] = Field(default_factory=list)
    trymode: bool = False


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
    contact: Optional[str] = None
    description: Optional[str] = None
    license: Optional[str] = "unset"
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


class SnapAppInfo(BaseModel):
    snap: Optional[str] = None
    name: str
    desktop_file: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("desktop-file", "desktop_file"),
        serialization_alias="desktop-file",
    )
    daemon: Optional[str] = None
    daemon_scope: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("daemon-scope", "daemon_scope"),
        serialization_alias="daemon-scope",
    )
    enabled: Optional[bool] = None
    active: Optional[bool] = None
    common_id: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("common-id", "common_id"),
        serialization_alias="common-id",
    )
    activators: Optional[list[dict]] = None


class AppsResponse(BaseResponse):
    result: list[SnapAppInfo]
