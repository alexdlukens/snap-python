from abc import ABC, abstractmethod

import httpx

from snap_python.schemas.changes import ChangesResponse


class SnapdAPIError(Exception):
    """
    General Exception raised for errors in the Snapd API.
    """

    pass


class AbstractSnapsClient(ABC):  # pragma: no cover
    @abstractmethod
    async def request(self, method: str, endpoint: str, **kwargs) -> httpx.Response:
        pass

    @abstractmethod
    async def request_raw(self, method: str, endpoint: str, **kwargs) -> httpx.Response:
        pass

    @abstractmethod
    async def get_changes_by_id(self, change_id: str) -> ChangesResponse:
        pass


def going_to_reload_daemon(changes: ChangesResponse | None) -> bool:
    """
    Determines if a daemon reload is required based on the provided changes.

    :param changes: An instance of ChangesResponse or None.
    :type changes: ChangesResponse | None

    :returns: True if a daemon reload or restart is required, False otherwise.
    :rtype: bool
    """

    if changes is None or not isinstance(changes, ChangesResponse):
        return False

    if changes.maintenance and changes.maintenance.kind in [
        "daemon-reload",
        "daemon-restart",
    ]:
        return True

    return False
