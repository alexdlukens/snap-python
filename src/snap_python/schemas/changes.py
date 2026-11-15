from pydantic import AliasChoices, AwareDatetime, BaseModel, Field

from snap_python.schemas.common import BaseErrorResult, BaseResponse


class MaintenanceInfo(BaseModel):
    kind: str
    message: str


class ProgressInfo(BaseModel):
    label: str
    done: int
    total: int


class Task(BaseModel):
    id: str
    kind: str
    summary: str
    status: str
    progress: ProgressInfo
    log: list[str] | None = None
    spawn_time: AwareDatetime = Field(
        validation_alias=AliasChoices("spawn-time", "spawn_time"),
        serialization_alias="spawn-time",
    )
    ready_time: AwareDatetime | None = Field(
        validation_alias=AliasChoices("ready-time", "ready_time"),
        serialization_alias="ready-time",
        default=None,
    )
    data: dict | None = None


class ChangesResult(BaseModel):
    id: str
    kind: str
    summary: str
    status: str
    # snapd tags tasks with ``omitempty``, and taskless changes exist: a
    # repeated connect, or any change whose tasks have not been built yet.
    tasks: list[Task] = Field(default_factory=list)
    ready: bool
    spawn_time: AwareDatetime = Field(
        validation_alias=AliasChoices("spawn-time", "spawn_time"),
        serialization_alias="spawn-time",
    )
    ready_time: AwareDatetime | None = Field(
        validation_alias=AliasChoices("ready-time", "ready_time"),
        serialization_alias="ready-time",
        default=None,
    )
    err: str | None = None
    data: dict | None = None

    @property
    def overall_progress(self) -> ProgressInfo:
        if not self.tasks:
            return ProgressInfo(label="Overall", done=0, total=-1)
        total = sum(task.progress.total for task in self.tasks)
        done = sum(task.progress.done for task in self.tasks)

        return ProgressInfo(label="Overall", done=done, total=total)


class ChangesResponse(BaseResponse):
    result: ChangesResult | BaseErrorResult
    maintenance: MaintenanceInfo | None = None

    @property
    def ready(self) -> bool:
        if isinstance(self.result, BaseErrorResult):
            return True
        return self.result.ready


class ChangesListResponse(BaseResponse):
    """Response of ``GET /v2/changes``.

    snapd always returns a JSON array, empty rather than ``null`` when no
    change matches, so :attr:`changes` is never ``None``.
    """

    result: list[ChangesResult] | BaseErrorResult
    maintenance: MaintenanceInfo | None = None

    @property
    def changes(self) -> list[ChangesResult]:
        if isinstance(self.result, BaseErrorResult):
            return []
        return self.result
