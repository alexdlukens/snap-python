import asyncio
import functools
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Awaitable, Callable, TypeVar

import httpx

from snap_python.schemas.changes import ChangesResponse
from snap_python.schemas.common import BaseErrorResult

logger = logging.getLogger("snap_python.utils")

T = TypeVar("T")

#: HTTP status codes that indicate a transient condition worth retrying.
TRANSIENT_HTTP_STATUS_CODES = frozenset({429}) | frozenset(range(500, 600))

#: HTTP methods that are safe to retry without risking duplicated side effects.
IDEMPOTENT_HTTP_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

#: Exceptions that indicate a transient transport level failure.
TRANSIENT_EXCEPTIONS: tuple[type[BaseException], ...] = (
    httpx.TransportError,
    httpx.TimeoutException,
)

RetryPredicate = Callable[[BaseException, tuple, dict], bool]


class SnapdAPIError(httpx.HTTPStatusError):
    """Error raised for a non-2xx response from snapd.

    Subclasses :class:`httpx.HTTPStatusError` so retry predicates and existing
    ``except httpx.HTTPStatusError`` handlers keep working, while exposing the
    parsed snapd error envelope (``kind`` and ``value``).

    :param message: Human readable error message.
    :param status_code: HTTP status code of the response, when there is one.
    :param kind: snapd error kind, for example ``snap-change-conflict``.
    :param value: Kind-specific payload from the snapd error envelope.
    :param request: Request that produced the error, when known.
    :param response: Response that produced the error, when known.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        kind: str | None = None,
        value: Any = None,
        request: httpx.Request | None = None,
        response: httpx.Response | None = None,
    ) -> None:
        if response is not None and request is None:
            request = response.request
        if status_code is None and response is not None:
            status_code = response.status_code
        super().__init__(message, request=request, response=response)
        self.status_code = status_code
        self.kind = kind
        self.value = value
        self.message = message


def is_transient_exception(exc: BaseException) -> bool:
    """Return True if ``exc`` is a transient error that is safe to retry.

    HTTP 4xx responses (other than 429) are never transient: retrying them
    cannot succeed and only delays surfacing the error to the caller.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        if exc.response is None:
            return False
        return exc.response.status_code in TRANSIENT_HTTP_STATUS_CODES
    return isinstance(exc, TRANSIENT_EXCEPTIONS)


def async_retry(
    exceptions: tuple[type[BaseException], ...] | type[BaseException] = httpx.HTTPError,
    tries: int = 3,
    delay: float = 1.0,
    backoff: float = 1.0,
    retry_if: RetryPredicate | None = None,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Asynchronous equivalent of ``retry.retry``.

    Unlike the decorators from the ``retry`` package this helper awaits the
    wrapped coroutine and uses :func:`asyncio.sleep`, so the event loop is never
    blocked while waiting to retry.

    :param exceptions: Exception type(s) that are candidates for a retry.
    :param tries: Maximum number of attempts (including the first one).
    :param delay: Seconds to wait before the first retry.
    :param backoff: Multiplier applied to the delay after each failed attempt.
    :param retry_if: Optional predicate receiving ``(exception, args, kwargs)``.
        When provided it decides whether a caught exception should be retried;
        by default only transient errors (:func:`is_transient_exception`) are.
    """

    if tries < 1:
        raise ValueError("tries must be >= 1")

    predicate = retry_if or (lambda exc, args, kwargs: is_transient_exception(exc))

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            current_delay = delay
            for attempt in range(1, tries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as exc:
                    if attempt >= tries or not predicate(exc, args, kwargs):
                        raise
                    logger.debug(
                        "Retrying %s after attempt %d/%d failed with %s: %s",
                        getattr(func, "__name__", func),
                        attempt,
                        tries,
                        type(exc).__name__,
                        exc,
                    )
                    await asyncio.sleep(current_delay)
                    current_delay *= backoff
            raise AssertionError("unreachable")  # pragma: no cover

        return wrapper

    return decorator


async def wait_for_change(
    client: "AbstractSnapsClient",
    change_id: str,
    timeout: float | None = None,
    poll_interval: float = 0.5,
    progress_callback: Callable[[ChangesResponse], None] | None = None,
) -> ChangesResponse:
    """Poll ``change_id`` until the change is ready or fails.

    :param client: Client used to query the change.
    :param change_id: Identifier of the change to poll.
    :param timeout: Maximum number of seconds to wait. ``None`` waits forever.
    :param poll_interval: Seconds between two polls.
    :param progress_callback: Optional callable invoked with every intermediate
        :class:`ChangesResponse`.

    :returns: The final :class:`ChangesResponse` (``ready`` is True).

    :raises SnapdAPIError: If the change reports an error, or if the timeout
        expires.
    :raises httpx.HTTPError: If polling fails with an error that is not a
        transient daemon reload.
    """
    deadline = None if timeout is None else time.monotonic() + timeout
    previous_changes: ChangesResponse | None = None

    while True:
        try:
            changes = await client.get_changes_by_id(change_id)
        except httpx.HTTPError:
            if previous_changes is not None and going_to_reload_daemon(
                previous_changes
            ):
                logger.debug("Waiting for snapd daemon to reload")
            else:
                raise
        else:
            if progress_callback is not None:
                progress_callback(changes)

            # Check for failures before looking at "ready": a failed change is
            # also reported as ready, so ordering matters here.
            if isinstance(changes.result, BaseErrorResult):
                raise SnapdAPIError(
                    f"Error waiting for change {change_id}: "
                    f"{changes.result.message}"
                )
            if changes.result.err:
                raise SnapdAPIError(
                    f"Error waiting for change {change_id}: {changes.result.err}"
                )
            if changes.ready:
                return changes

            previous_changes = changes

        if deadline is not None and time.monotonic() >= deadline:
            raise SnapdAPIError(
                f"Timed out after {timeout}s waiting for change {change_id}"
            )
        await asyncio.sleep(poll_interval)


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
