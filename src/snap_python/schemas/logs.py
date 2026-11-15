"""Models for the RFC 7464 JSON-seq stream served by ``GET /v2/logs``."""

from pydantic import BaseModel


class LogEntry(BaseModel):
    """One record of the ``application/json-seq`` log stream.

    Mirrors snapd's ``client.Log``: ``timestamp`` is RFC 3339 to microsecond
    precision, and ``pid`` is a **string** (it is taken verbatim from journald).
    All four keys are always present.
    """

    timestamp: str
    message: str
    sid: str
    pid: str
