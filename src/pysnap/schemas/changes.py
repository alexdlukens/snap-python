from pydantic import AliasChoices, AwareDatetime, BaseModel, Field

from pysnap.schemas.common import BaseErrorResult, BaseResponse


class Task(BaseModel):
    id: str
    kind: str
    summary: str
    status: str
    progress: dict
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
    tasks: list[Task]
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


class ChangesResponse(BaseResponse):
    result: ChangesResult | BaseErrorResult

    @property
    def ready(self) -> bool:
        if isinstance(self.result, BaseErrorResult):
            return False
        return self.result.ready
