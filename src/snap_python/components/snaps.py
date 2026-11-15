import logging
from pathlib import Path
from typing import Any

import httpx

from snap_python.schemas.changes import ChangesResponse
from snap_python.schemas.common import AsyncResponse
from snap_python.schemas.snaps import (
    AppsResponse,
    InstalledSnap,
    InstalledSnapListResponse,
    SingleInstalledSnapResponse,
)
from snap_python.utils import AbstractSnapsClient, SnapdAPIError, wait_for_change

logger = logging.getLogger("snap_python.components.snaps")


class SnapsEndpoints:
    def __init__(self, client: AbstractSnapsClient) -> None:
        self._client = client
        self.common_endpoint = "snaps"

    async def _wait_for_change(
        self,
        change_id: str,
        timeout: float | None = None,
        poll_interval: float = 0.5,
        progress_callback=None,
    ) -> ChangesResponse:
        """Wait for a snapd change to reach a terminal state.

        Thin wrapper around :func:`snap_python.utils.wait_for_change` bound to
        this endpoint's client.

        :param change_id: The change to wait for.
        :type change_id: str
        :param timeout: Maximum number of seconds to wait, None waits forever.
        :type timeout: float, optional
        :param poll_interval: Seconds between two polls.
        :type poll_interval: float, optional
        :param progress_callback: Optional callable receiving intermediate changes.
        :type progress_callback: callable, optional

        :returns: The final change response.
        :rtype: ChangesResponse

        :raises SnapdAPIError: If the change reports an error or times out.
        """
        return await wait_for_change(
            self._client,
            change_id,
            timeout=timeout,
            poll_interval=poll_interval,
            progress_callback=progress_callback,
        )

    async def list_installed_snaps(
        self,
        select: str | None = None,
        snaps: list[str] | None = None,
    ) -> InstalledSnapListResponse:
        """
        Asynchronously retrieves a list of installed snaps.

        :param select: Which revisions snapd should return. ``"all"`` returns
            every revision in each snap's sequence, inactive ones included;
            ``"enabled"`` returns only the revision snapd currently has
            enabled; ``"refresh-inhibited"`` returns only snaps whose refresh
            is inhibited, i.e. those carrying a ``refresh-inhibit`` field with
            the time the refresh may proceed. None (default) omits the
            parameter so snapd applies its own default (only the enabled
            revision of every snap).
        :type select: str, optional
        :param snaps: Only return these snap names. None (default) returns
            every installed snap. snapd receives the names as a single
            comma-separated ``snaps`` query parameter.
        :type snaps: list[str], optional

        :returns: The response containing the list of installed snaps.
        :rtype: InstalledSnapListResponse

        :raises SnapdAPIError: If snapd rejects the request, for example for an
            unknown ``select`` value (``kind`` is ``bad-request``).
        """
        params: dict[str, Any] = {}
        if select is not None:
            params["select"] = select
        if snaps:
            params["snaps"] = ",".join(snaps)

        response: httpx.Response = await self._client.request(
            "GET", self.common_endpoint, params=params
        )
        return InstalledSnapListResponse.model_validate_json(response.content)

    async def get_snap_info(self, snap: str) -> SingleInstalledSnapResponse:
        """
        Retrieves information about a specific snap.

        :param snap: The name of the snap to retrieve information for.
        :type snap: str

        :returns: The response containing information about the snap.
        :rtype: SingleInstalledSnapResponse

        :raises httpx.HTTPStatusError: If the response status code does not indicate success.
        """
        try:
            response: httpx.Response = await self._client.request(
                "GET", f"{self.common_endpoint}/{snap}"
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code != httpx.codes.NOT_FOUND:
                logger.debug(
                    "Bad status code from get_snap_info on snap %s: %s",
                    snap,
                    e.response.status_code,
                )
                if isinstance(e, SnapdAPIError):
                    # Already carries the parsed kind/value envelope.
                    raise
                raise SnapdAPIError(
                    f"Failed to get info for snap {snap}: "
                    f"HTTP {e.response.status_code}",
                    response=e.response,
                ) from e
            logger.debug("Snap %s is not installed (HTTP 404)", snap)
            return SingleInstalledSnapResponse.model_validate_json(e.response.content)

        return SingleInstalledSnapResponse.model_validate_json(response.content)

    async def get_installed_snap(self, snap: str) -> InstalledSnap | None:
        """
        Get information about an installed snap.

        :param snap: The name of the snap to inspect.
        :type snap: str

        :returns: The installed snap, or None if the snap is not installed.
        :rtype: InstalledSnap | None

        :raises SnapdAPIError: If snapd reports an unexpected error.
        """
        response = await self.get_snap_info(snap)
        if isinstance(response.result, InstalledSnap):
            return response.result
        if response.status_code == httpx.codes.NOT_FOUND:
            return None
        raise SnapdAPIError(
            f"Unexpected response while getting snap {snap}: "
            f"HTTP {response.status_code}"
        )

    async def is_snap_installed(self, snap: str) -> bool:
        """
        Check if a snap package is installed.

        :param snap: The name of the snap package to check.
        :type snap: str

        :returns: True if the snap package is installed, False otherwise.
        :rtype: bool
        """

        return await self.get_installed_snap(snap) is not None

    @staticmethod
    def _sideload_form_data(
        filename: str,
        channel: str | None = None,
        classic: bool = False,
        dangerous: bool = False,
        devmode: bool = False,
        jailmode: bool = False,
    ) -> dict[str, str]:
        """Build the multipart form snapd honors for a sideload.

        The daemon's multipart handler (``sideloadOrTrySnap`` in
        ``daemon/api_sideload_n_try.go``) only special-cases ``action ==
        "try"``; every other action is a path install. These field names match
        what snapd's own client writes (``client/snap_op.go``).

        :param filename: Path to the snap file, sent as ``snap-path``.
        :type filename: str
        :param channel: Optional channel to send with the sideload.
        :type channel: str, optional
        :param classic: Whether to request classic confinement.
        :type classic: bool
        :param dangerous: Whether to allow unasserted snaps.
        :type dangerous: bool
        :param devmode: Whether to request devmode.
        :type devmode: bool
        :param jailmode: Whether to request jailmode.
        :type jailmode: bool

        :returns: Form fields to send alongside the ``snap`` file part.
        :rtype: dict[str, str]
        """
        form_data = {"action": "install", "snap-path": filename}
        if channel is not None:
            form_data["channel"] = channel
        for key, value in (
            ("classic", classic),
            ("dangerous", dangerous),
            ("devmode", devmode),
            ("jailmode", jailmode),
        ):
            if value:
                form_data[key] = "true"
        return form_data

    @staticmethod
    def _multi_snap_payload(
        action: str,
        snaps: list[str] | None = None,
        *,
        transaction: str | None = None,
        validation_sets: list[str] | None = None,
        quota_group: str | None = None,
        ignore_running: bool = False,
        purge: bool = False,
        terminate: bool = False,
        time: str | None = None,
        hold_level: str | None = None,
    ) -> dict[str, Any]:
        """Build the JSON body of a multi-snap ``POST /v2/snaps`` request.

        Only options snapd accepts for the multi-snap form are emitted, and
        unset ones are omitted entirely. The daemon rejects the single-snap
        options ``channel``, ``revision``, ``devmode``, ``jailmode``,
        ``cohort-key``, ``leave-cohort``, ``prefer`` and
        ``allow-unsupported-instances`` for this form ("unsupported option
        provided for multi-snap operation"), so callers must use the
        single-snap methods for those.

        An empty ``snaps`` list is omitted from the body; snapd reads the
        missing field as "all snaps" for the ``refresh``, ``hold`` and
        ``unhold`` actions.

        :param action: The snapd action, for example ``"install"``.
        :type action: str
        :param snaps: Snap names to act on. None or empty is omitted.
        :type snaps: list[str], optional
        :param transaction: ``"per-snap"`` or ``"all-snaps"``; snapd only
            accepts it for install and refresh.
        :type transaction: str, optional
        :param validation_sets: Validation sets to enforce on a refresh.
        :type validation_sets: list[str], optional
        :param quota_group: Quota group to install into; snapd only accepts it
            for install.
        :type quota_group: str, optional
        :param ignore_running: Whether to proceed while the snap's apps run.
        :type ignore_running: bool
        :param purge: Also remove the snap's data (remove only).
        :type purge: bool
        :param terminate: Kill the snap's processes before removal (remove
            only).
        :type terminate: bool
        :param time: When the hold expires, ``"forever"`` or an RFC3339
            timestamp (hold only).
        :type time: str, optional
        :param hold_level: ``"auto-refresh"`` or ``"general"`` (hold only).
        :type hold_level: str, optional

        :returns: JSON-serialisable request body.
        :rtype: dict[str, Any]
        """
        payload: dict[str, Any] = {"action": action}
        if snaps:
            payload["snaps"] = list(snaps)
        if transaction is not None:
            payload["transaction"] = transaction
        if validation_sets:
            payload["validation-sets"] = list(validation_sets)
        if quota_group is not None:
            payload["quota-group"] = quota_group
        if ignore_running:
            payload["ignore-running"] = True
        if purge:
            payload["purge"] = True
        if terminate:
            payload["terminate"] = True
        if time is not None:
            payload["time"] = time
        if hold_level is not None:
            payload["hold-level"] = hold_level
        return payload

    async def _post_snap_action(
        self,
        snap: str,
        payload: dict[str, Any],
        *,
        wait: bool,
        timeout: float | None,
    ) -> AsyncResponse | ChangesResponse:
        """POST ``payload`` to ``/v2/snaps/{snap}`` and optionally wait.

        :param snap: Name of the snap the action applies to.
        :type snap: str
        :param payload: JSON request body, including the ``action`` field.
        :type payload: dict[str, Any]
        :param wait: Whether to wait for the resulting change.
        :type wait: bool
        :param timeout: Maximum number of seconds to wait, None waits forever.
        :type timeout: float, optional

        :returns: AsyncResponse, or ChangesResponse when ``wait`` is True.
        :rtype: AsyncResponse | ChangesResponse

        :raises SnapdAPIError: If snapd rejects the action.
        """
        raw_response: httpx.Response = await self._client.request(
            "POST", f"{self.common_endpoint}/{snap}", json=payload
        )
        response = AsyncResponse.model_validate_json(raw_response.content)
        if wait:
            return await self._wait_for_change(response.change, timeout=timeout)
        return response

    async def _post_multi_snap_action(
        self,
        payload: dict[str, Any],
        *,
        wait: bool,
        timeout: float | None,
    ) -> AsyncResponse | ChangesResponse:
        """POST ``payload`` to ``/v2/snaps`` and optionally wait.

        :param payload: JSON request body, including the ``action`` field.
        :type payload: dict[str, Any]
        :param wait: Whether to wait for the resulting change.
        :type wait: bool
        :param timeout: Maximum number of seconds to wait, None waits forever.
        :type timeout: float, optional

        :returns: AsyncResponse, or ChangesResponse when ``wait`` is True.
        :rtype: AsyncResponse | ChangesResponse

        :raises SnapdAPIError: If snapd rejects the action.
        """
        raw_response: httpx.Response = await self._client.request(
            "POST", self.common_endpoint, json=payload
        )
        response = AsyncResponse.model_validate_json(raw_response.content)
        if wait:
            return await self._wait_for_change(response.change, timeout=timeout)
        return response

    async def install_snap(
        self,
        snap: str,
        channel: str | None = None,
        classic: bool = False,
        dangerous: bool = False,
        devmode: bool = False,
        jailmode: bool = False,
        revision: int = None,
        filename: str = None,
        wait: bool = False,
        timeout: float | None = None,
    ) -> AsyncResponse | ChangesResponse:
        """
        Install or sideload a snap.

        To sideload a snap, provide the filename parameter with the path to the snap file.
        snapd accepts a locally injected snap whose assertion is valid without
        ``dangerous``; that flag is only needed for unasserted snaps and is
        passed through untouched.

        :param snap: Name of the snap to install.
        :type snap: str
        :param channel: Channel to install from. None (default) lets snapd use
            its own default channel.
        :type channel: str, optional
        :param classic: Install with classic confinement, defaults to False.
        :type classic: bool, optional
        :param dangerous: Install the given snap files even if there are no pre-acknowledged signatures for them, meaning they are not verified and could be dangerous if true (optional, implied by devmode), defaults to False.
        :type dangerous: bool, optional
        :param devmode: Install with devmode, defaults to False.
        :type devmode: bool, optional
        :param jailmode: Install snap with jailmode, defaults to False.
        :type jailmode: bool, optional
        :param revision: Install a specific revision of the snap, defaults to None.
        :type revision: int, optional
        :param filename: Path to snap to sideload, defaults to None.
        :type filename: str, optional
        :param wait: Whether to wait for snap to install. If not waiting, will return async response with change id, defaults to False.
        :type wait: bool, optional
        :param timeout: Maximum number of seconds to wait for the install to finish, defaults to None (wait forever).
        :type timeout: float, optional

        :raises FileNotFoundError: If the specified snap file does not exist.
        :raises SnapdAPIError: If there is an error during the snap install.

        :returns: If wait is True, will return ChangesResponse. Otherwise, will return AsyncResponse.
        :rtype: AsyncResponse | ChangesResponse
        """
        request_data = {
            "action": "install",
            "classic": classic,
            "dangerous": dangerous,
            "devmode": devmode,
            "jailmode": jailmode,
        }
        if channel is not None:
            request_data["channel"] = channel
        if revision:
            request_data["revision"] = revision
        if filename:
            # sideload
            snap_path = Path(filename)
            if not snap_path.exists():
                raise FileNotFoundError(f"File {filename} does not exist")
            form_data = self._sideload_form_data(
                filename=str(snap_path),
                channel=channel,
                classic=classic,
                dangerous=dangerous,
                devmode=devmode,
                jailmode=jailmode,
            )
            with open(snap_path, "rb") as snap_file:
                raw_response: httpx.Response = await self._client.request(
                    "POST",
                    f"{self.common_endpoint}",
                    data=form_data,
                    files={"snap": (snap_path.name, snap_file)},
                )
        else:
            # install from default snap store
            raw_response: httpx.Response = await self._client.request(
                "POST", f"{self.common_endpoint}/{snap}", json=request_data
            )
        response = AsyncResponse.model_validate_json(raw_response.content)
        if wait:
            return await self._wait_for_change(response.change, timeout=timeout)
        return response

    async def remove_snap(
        self,
        snap: str,
        purge: bool = False,
        terminate: bool = False,
        wait: bool = False,
        timeout: float | None = None,
    ) -> AsyncResponse | ChangesResponse:
        """
        Asynchronously removes a snap package.

        :param snap: The name of the snap package to remove.
        :type snap: str
        :param purge: If True, purges the snap package. Defaults to False.
        :type purge: bool, optional
        :param terminate: If True, terminates the snap package. Defaults to False.
        :type terminate: bool, optional
        :param wait: If True, waits for the removal process to complete. Defaults to False.
        :type wait: bool, optional
        :param timeout: Maximum number of seconds to wait for the removal to finish, defaults to None (wait forever).
        :type timeout: float, optional

        :returns: The response from the snapd API, either an asynchronous response or a changes response if waiting for completion.
        :rtype: AsyncResponse | ChangesResponse

        :raises SnapdAPIError: If there is an error in the snap removal process.
        """
        request_data = {
            "action": "remove",
            "purge": purge,
            "terminate": terminate,
        }

        raw_response: httpx.Response = await self._client.request(
            "POST", f"{self.common_endpoint}/{snap}", json=request_data
        )
        response = AsyncResponse.model_validate_json(raw_response.content)

        if wait:
            return await self._wait_for_change(response.change, timeout=timeout)

        return response

    async def refresh_snap(
        self,
        snap: str,
        channel: str | None = None,
        classic: bool = False,
        dangerous: bool = False,
        devmode: bool = False,
        ignore_validation: bool = False,
        jailmode: bool = False,
        revision: int = None,
        filename: str = None,
        wait: bool = False,
        timeout: float | None = None,
    ) -> AsyncResponse | ChangesResponse:
        """
        Refreshes a snap package.

        :param snap: The name of the snap package to refresh.
        :type snap: str
        :param channel: Channel to refresh from. None (default) keeps the
            currently tracked channel.
        :type channel: str, optional
        :param classic: Whether to use classic confinement. Defaults to False.
        :type classic: bool, optional
        :param dangerous: Whether to allow installation of unasserted snaps. Defaults to False.
        :type dangerous: bool, optional
        :param devmode: Whether to use development mode. Defaults to False.
        :type devmode: bool, optional
        :param ignore_validation: Whether to ignore validation. Defaults to False.
        :type ignore_validation: bool, optional
        :param jailmode: Whether to use jail mode. Defaults to False.
        :type jailmode: bool, optional
        :param revision: The specific revision to refresh to. Defaults to None.
        :type revision: int, optional
        :param filename: The path to the snap file for sideloading. Defaults to None.
        :type filename: str, optional
        :param wait: Whether to wait for the refresh operation to complete. Defaults to False.
        :type wait: bool, optional
        :param timeout: Maximum number of seconds to wait for the refresh to finish, defaults to None (wait forever).
        :type timeout: float, optional

        :returns: The response from the refresh operation.
        :rtype: AsyncResponse | ChangesResponse

        :raises FileNotFoundError: If the specified snap file does not exist.
        :raises SnapdAPIError: If there is an error during the snap refresh.
        """
        request_data = {
            "action": "refresh",
            "classic": classic,
            "dangerous": dangerous,
            "devmode": devmode,
            "ignore_validation": ignore_validation,
            "jailmode": jailmode,
        }
        if channel is not None:
            request_data["channel"] = channel
        if revision:
            request_data["revision"] = revision
        if filename:
            # Sideload. The daemon's multipart handler only treats
            # action == "try" specially; every other value is a path install,
            # so use "install" here instead of "refresh".
            snap_path = Path(filename)
            if not snap_path.exists():
                raise FileNotFoundError(f"File {filename} does not exist")
            form_data = self._sideload_form_data(
                filename=str(snap_path),
                channel=channel,
                classic=classic,
                dangerous=dangerous,
                devmode=devmode,
                jailmode=jailmode,
            )
            with open(snap_path, "rb") as snap_file:
                raw_response: httpx.Response = await self._client.request(
                    "POST",
                    f"{self.common_endpoint}",
                    data=form_data,
                    files={"snap": (snap_path.name, snap_file)},
                )
        else:
            # refresh from default snap store
            raw_response: httpx.Response = await self._client.request(
                "POST", f"{self.common_endpoint}/{snap}", json=request_data
            )
        response = AsyncResponse.model_validate_json(raw_response.content)
        if wait:
            return await self._wait_for_change(response.change, timeout=timeout)
        return response

    async def install_snaps(
        self,
        snaps: list[str],
        transaction: str | None = None,
        validation_sets: list[str] | None = None,
        quota_group: str | None = None,
        ignore_running: bool = False,
        wait: bool = False,
        timeout: float | None = None,
    ) -> AsyncResponse | ChangesResponse:
        """
        Install several snaps in a single change (JSON ``POST /v2/snaps``).

        This is the only form that can put multiple snaps in one change,
        group them into a transaction and assign a quota group. snapd rejects
        the single-snap options (channel, revision, devmode, jailmode,
        cohort-key, leave-cohort, prefer) here, so per-snap overrides require
        calling :meth:`install_snap` once per snap.

        :param snaps: Names of the snaps to install. Must not be empty; snapd
            answers "cannot install zero snaps" otherwise.
        :type snaps: list[str]
        :param transaction: ``"per-snap"`` treats every snap as its own
            transaction, ``"all-snaps"`` reverts everything when one snap
            fails. None (default) lets snapd use its own default.
        :type transaction: str, optional
        :param validation_sets: Validation sets to enforce. snapd accepts the
            field for install but only acts on it while refreshing; use
            :meth:`refresh_snaps` to enforce them.
        :type validation_sets: list[str], optional
        :param quota_group: Quota group the snaps should be placed in. snapd
            only accepts a quota group on install.
        :type quota_group: str, optional
        :param ignore_running: Install even if the snaps' applications are
            running. Defaults to False.
        :type ignore_running: bool
        :param wait: Whether to wait for the change to reach a terminal state.
            Defaults to False.
        :type wait: bool
        :param timeout: Maximum number of seconds to wait, defaults to None
            (wait forever).
        :type timeout: float, optional

        :returns: AsyncResponse, or ChangesResponse when ``wait`` is True.
        :rtype: AsyncResponse | ChangesResponse

        :raises SnapdAPIError: If snapd rejects the install.
        """
        payload = self._multi_snap_payload(
            "install",
            snaps,
            transaction=transaction,
            validation_sets=validation_sets,
            quota_group=quota_group,
            ignore_running=ignore_running,
        )
        return await self._post_multi_snap_action(payload, wait=wait, timeout=timeout)

    async def refresh_snaps(
        self,
        snaps: list[str] | None = None,
        transaction: str | None = None,
        validation_sets: list[str] | None = None,
        ignore_running: bool = False,
        wait: bool = False,
        timeout: float | None = None,
    ) -> AsyncResponse | ChangesResponse:
        """
        Refresh several snaps, or every installed snap, in one change.

        ``snaps=None`` (or an empty list) refreshes **every** installed snap:
        the ``snaps`` field is omitted from the request and snapd treats that
        as a full refresh, also updating the validation set assertions.
        :meth:`refresh_all_snaps` is a convenience wrapper for that case.

        ``validation_sets`` enforces validation sets instead of refreshing
        named snaps; snapd rejects it together with a non-empty ``snaps`` list
        ("snap names cannot be specified with validation sets to enforce").

        :param snaps: Names of the snaps to refresh. None or empty refreshes
            every installed snap.
        :type snaps: list[str], optional
        :param transaction: ``"per-snap"`` or ``"all-snaps"``; snapd defaults
            to ``"per-snap"`` when omitted.
        :type transaction: str, optional
        :param validation_sets: Validation sets to enforce, for example
            ``"account/name"`` or ``"account/name=42"``. Must be used without
            snap names.
        :type validation_sets: list[str], optional
        :param ignore_running: Refresh even if the snaps' applications are
            running. Defaults to False.
        :type ignore_running: bool
        :param wait: Whether to wait for the change to reach a terminal state.
            Defaults to False.
        :type wait: bool
        :param timeout: Maximum number of seconds to wait, defaults to None
            (wait forever).
        :type timeout: float, optional

        :returns: AsyncResponse, or ChangesResponse when ``wait`` is True.
        :rtype: AsyncResponse | ChangesResponse

        :raises SnapdAPIError: If snapd rejects the refresh.
        """
        payload = self._multi_snap_payload(
            "refresh",
            snaps,
            transaction=transaction,
            validation_sets=validation_sets,
            ignore_running=ignore_running,
        )
        return await self._post_multi_snap_action(payload, wait=wait, timeout=timeout)

    async def refresh_all_snaps(
        self,
        transaction: str | None = None,
        wait: bool = False,
        timeout: float | None = None,
    ) -> AsyncResponse | ChangesResponse:
        """
        Refresh every installed snap.

        Thin wrapper around :meth:`refresh_snaps` with no snap names, which is
        how snapd expresses a full refresh.

        :param transaction: ``"per-snap"`` or ``"all-snaps"``. None (default)
            lets snapd use ``"per-snap"``.
        :type transaction: str, optional
        :param wait: Whether to wait for the change to reach a terminal state.
            Defaults to False.
        :type wait: bool
        :param timeout: Maximum number of seconds to wait, defaults to None
            (wait forever).
        :type timeout: float, optional

        :returns: AsyncResponse, or ChangesResponse when ``wait`` is True.
        :rtype: AsyncResponse | ChangesResponse

        :raises SnapdAPIError: If snapd rejects the refresh.
        """
        return await self.refresh_snaps(
            transaction=transaction, wait=wait, timeout=timeout
        )

    async def remove_snaps(
        self,
        snaps: list[str],
        purge: bool = False,
        terminate: bool = False,
        wait: bool = False,
        timeout: float | None = None,
    ) -> AsyncResponse | ChangesResponse:
        """
        Remove several snaps in a single change (JSON ``POST /v2/snaps``).

        snapd accepts no transaction type for removal and no per-snap options;
        ``purge`` and ``terminate`` apply to every listed snap.

        :param snaps: Names of the snaps to remove.
        :type snaps: list[str]
        :param purge: Also remove the snaps' data. Defaults to False.
        :type purge: bool
        :param terminate: Kill the snaps' running processes before removal,
            which may lose data. Defaults to False.
        :type terminate: bool
        :param wait: Whether to wait for the change to reach a terminal state.
            Defaults to False.
        :type wait: bool
        :param timeout: Maximum number of seconds to wait, defaults to None
            (wait forever).
        :type timeout: float, optional

        :returns: AsyncResponse, or ChangesResponse when ``wait`` is True.
        :rtype: AsyncResponse | ChangesResponse

        :raises SnapdAPIError: If snapd rejects the removal.
        """
        payload = self._multi_snap_payload(
            "remove", snaps, purge=purge, terminate=terminate
        )
        return await self._post_multi_snap_action(payload, wait=wait, timeout=timeout)

    async def hold_snap(
        self,
        snap: str,
        time: str = "forever",
        hold_level: str = "general",
        wait: bool = False,
        timeout: float | None = None,
    ) -> AsyncResponse | ChangesResponse:
        """
        Hold refreshes of a single snap.

        :param snap: The snap whose refreshes should be held.
        :type snap: str
        :param time: ``"forever"`` or an RFC3339 timestamp, defaults to
            ``"forever"``. snapd validates the format and answers 400 for
            anything else.
        :type time: str
        :param hold_level: ``"general"`` (default) holds every refresh,
            ``"auto-refresh"`` only holds automatic refreshes so an explicit
            refresh still works. Current snapd requires this field for the
            ``hold`` action and rejects any other value.
        :type hold_level: str
        :param wait: Whether to wait for the change to reach a terminal state.
            Defaults to False.
        :type wait: bool
        :param timeout: Maximum number of seconds to wait, defaults to None
            (wait forever).
        :type timeout: float, optional

        :returns: AsyncResponse, or ChangesResponse when ``wait`` is True.
        :rtype: AsyncResponse | ChangesResponse

        :raises SnapdAPIError: If snapd rejects the hold, for example because
            ``time`` is not ``"forever"``/RFC3339 or ``hold_level`` is
            unknown.
        """
        payload = {
            "action": "hold",
            "time": time,
            "hold-level": hold_level,
        }
        return await self._post_snap_action(snap, payload, wait=wait, timeout=timeout)

    async def unhold_snap(
        self,
        snap: str,
        wait: bool = False,
        timeout: float | None = None,
    ) -> AsyncResponse | ChangesResponse:
        """
        Release a refresh hold on a single snap.

        Only the action is sent: snapd rejects both ``time`` and
        ``hold-level`` for any action other than ``hold`` ("time can only be
        specified for the \"hold\" action").

        :param snap: The snap whose hold should be released.
        :type snap: str
        :param wait: Whether to wait for the change to reach a terminal state.
            Defaults to False.
        :type wait: bool
        :param timeout: Maximum number of seconds to wait, defaults to None
            (wait forever).
        :type timeout: float, optional

        :returns: AsyncResponse, or ChangesResponse when ``wait`` is True.
        :rtype: AsyncResponse | ChangesResponse

        :raises SnapdAPIError: If snapd rejects the request.
        """
        return await self._post_snap_action(
            snap, {"action": "unhold"}, wait=wait, timeout=timeout
        )

    async def hold_snaps(
        self,
        snaps: list[str],
        time: str = "forever",
        hold_level: str = "general",
        wait: bool = False,
        timeout: float | None = None,
    ) -> AsyncResponse | ChangesResponse:
        """
        Hold refreshes of several snaps in one change.

        :param snaps: The snaps whose refreshes should be held. Must not be
            empty; an empty list is sent as a system-wide hold, for which
            snapd only accepts ``hold_level="auto-refresh"``.
        :type snaps: list[str]
        :param time: ``"forever"`` or an RFC3339 timestamp, defaults to
            ``"forever"``.
        :type time: str
        :param hold_level: ``"general"`` (default) or ``"auto-refresh"``.
        :type hold_level: str
        :param wait: Whether to wait for the change to reach a terminal state.
            Defaults to False.
        :type wait: bool
        :param timeout: Maximum number of seconds to wait, defaults to None
            (wait forever).
        :type timeout: float, optional

        :returns: AsyncResponse, or ChangesResponse when ``wait`` is True.
        :rtype: AsyncResponse | ChangesResponse

        :raises SnapdAPIError: If snapd rejects the hold.
        """
        payload = self._multi_snap_payload(
            "hold", snaps, time=time, hold_level=hold_level
        )
        return await self._post_multi_snap_action(payload, wait=wait, timeout=timeout)

    async def unhold_snaps(
        self,
        snaps: list[str],
        wait: bool = False,
        timeout: float | None = None,
    ) -> AsyncResponse | ChangesResponse:
        """
        Release refresh holds on several snaps in one change.

        No ``time``/``hold-level`` is sent: snapd rejects either field for
        anything but the ``hold`` action.

        :param snaps: The snaps whose holds should be released. Must not be
            empty; an omitted list is a system-wide unhold.
        :type snaps: list[str]
        :param wait: Whether to wait for the change to reach a terminal state.
            Defaults to False.
        :type wait: bool
        :param timeout: Maximum number of seconds to wait, defaults to None
            (wait forever).
        :type timeout: float, optional

        :returns: AsyncResponse, or ChangesResponse when ``wait`` is True.
        :rtype: AsyncResponse | ChangesResponse

        :raises SnapdAPIError: If snapd rejects the request.
        """
        payload = self._multi_snap_payload("unhold", snaps)
        return await self._post_multi_snap_action(payload, wait=wait, timeout=timeout)

    async def hold_all_snaps(
        self,
        time: str = "forever",
        hold_level: str = "auto-refresh",
        wait: bool = False,
        timeout: float | None = None,
    ) -> AsyncResponse | ChangesResponse:
        """
        Hold refreshes for every installed snap.

        snapd implements this as a configuration change of ``refresh.hold`` on
        the ``core`` snap (``snapHoldMany`` with an empty ``snaps`` list), not
        as a per-snap hold. Only ``hold_level="auto-refresh"`` is supported
        for this form: snapd answers 400 with "holding general refreshes for
        all snaps is not supported" for ``"general"``.

        :param time: ``"forever"`` or an RFC3339 timestamp, defaults to
            ``"forever"``.
        :type time: str
        :param hold_level: Only ``"auto-refresh"`` (the default) is accepted
            by snapd for the system-wide form.
        :type hold_level: str
        :param wait: Whether to wait for the change to reach a terminal state.
            Defaults to False.
        :type wait: bool
        :param timeout: Maximum number of seconds to wait, defaults to None
            (wait forever).
        :type timeout: float, optional

        :returns: AsyncResponse, or ChangesResponse when ``wait`` is True.
        :rtype: AsyncResponse | ChangesResponse

        :raises SnapdAPIError: If snapd rejects the hold.
        """
        payload = self._multi_snap_payload("hold", time=time, hold_level=hold_level)
        return await self._post_multi_snap_action(payload, wait=wait, timeout=timeout)

    async def unhold_all_snaps(
        self,
        wait: bool = False,
        timeout: float | None = None,
    ) -> AsyncResponse | ChangesResponse:
        """
        Release the system-wide refresh hold.

        snapd implements this as a ``refresh.hold`` configuration change on
        the ``core`` snap (``snapUnholdMany`` with an empty ``snaps`` list).

        :param wait: Whether to wait for the change to reach a terminal state.
            Defaults to False.
        :type wait: bool
        :param timeout: Maximum number of seconds to wait, defaults to None
            (wait forever).
        :type timeout: float, optional

        :returns: AsyncResponse, or ChangesResponse when ``wait`` is True.
        :rtype: AsyncResponse | ChangesResponse

        :raises SnapdAPIError: If snapd rejects the request.
        """
        payload = self._multi_snap_payload("unhold")
        return await self._post_multi_snap_action(payload, wait=wait, timeout=timeout)

    async def revert_snap(
        self,
        snap: str,
        revision: int | None = None,
        wait: bool = False,
        timeout: float | None = None,
    ) -> AsyncResponse | ChangesResponse:
        """
        Revert a snap to its previous revision, or to a specific one.

        :param snap: The snap to revert.
        :type snap: str
        :param revision: Revision to revert to. None (default) rolls the snap
            back one revision, like ``snap revert``; snapd accepts the
            ``revision`` field for ``revert``.
        :type revision: int, optional
        :param wait: Whether to wait for the change to reach a terminal state.
            Defaults to False.
        :type wait: bool
        :param timeout: Maximum number of seconds to wait, defaults to None
            (wait forever).
        :type timeout: float, optional

        :returns: AsyncResponse, or ChangesResponse when ``wait`` is True.
        :rtype: AsyncResponse | ChangesResponse

        :raises SnapdAPIError: If snapd rejects the revert, for example with
            kind ``snap-change-conflict`` when another change for the snap is
            in progress.
        """
        payload: dict[str, Any] = {"action": "revert"}
        if revision is not None:
            payload["revision"] = revision
        return await self._post_snap_action(snap, payload, wait=wait, timeout=timeout)

    async def switch_channel(
        self,
        snap: str,
        channel: str | None = None,
        cohort_key: str | None = None,
        leave_cohort: bool = False,
        wait: bool = False,
        timeout: float | None = None,
    ) -> AsyncResponse | ChangesResponse:
        """
        Switch the channel (and/or cohort) a snap tracks without refreshing.

        snapd takes no ``revision`` for ``switch`` ("switch takes no
        revision") and refuses the request while another change for the snap
        is in progress, answering 409 with kind ``snap-change-conflict``.

        :param snap: The snap to switch.
        :type snap: str
        :param channel: Channel to track, for example ``"latest/edge"``. snapd
            validates it with its channel parser. None (default) keeps the
            currently tracked channel, which is what a cohort-only switch
            needs.
        :type channel: str, optional
        :param cohort_key: Cohort to join. snapd rejects combining it with
            ``leave_cohort`` ("cannot specify both cohort-key and
            leave-cohort").
        :type cohort_key: str, optional
        :param leave_cohort: Leave the current cohort. Defaults to False.
        :type leave_cohort: bool
        :param wait: Whether to wait for the change to reach a terminal state.
            Defaults to False.
        :type wait: bool
        :param timeout: Maximum number of seconds to wait, defaults to None
            (wait forever).
        :type timeout: float, optional

        :returns: AsyncResponse, or ChangesResponse when ``wait`` is True.
        :rtype: AsyncResponse | ChangesResponse

        :raises SnapdAPIError: If snapd rejects the switch, for example because
            the channel is invalid or the cohort options conflict.
        """
        payload: dict[str, Any] = {"action": "switch"}
        if channel is not None:
            payload["channel"] = channel
        if cohort_key is not None:
            payload["cohort-key"] = cohort_key
        if leave_cohort:
            payload["leave-cohort"] = True
        return await self._post_snap_action(snap, payload, wait=wait, timeout=timeout)

    async def disable_snap(
        self,
        snap: str,
        wait: bool = False,
        timeout: float | None = None,
    ) -> AsyncResponse | ChangesResponse:
        """
        Disables a snap package.

        :param snap: The name of the snap package to disable.
        :type snap: str
        :param wait: Whether to wait for the disable operation to complete. Defaults to False.
        :type wait: bool, optional
        :param timeout: Maximum number of seconds to wait for the disable to finish, defaults to None (wait forever).
        :type timeout: float, optional

        :returns: The response from the disable operation.
        :rtype: AsyncResponse | ChangesResponse

        :raises SnapdAPIError: If there is an error during the snap disable operation.
        """
        request_data = {
            "action": "disable",
        }

        raw_response: httpx.Response = await self._client.request(
            "POST", f"{self.common_endpoint}/{snap}", json=request_data
        )
        response = AsyncResponse.model_validate_json(raw_response.content)

        if wait:
            return await self._wait_for_change(response.change, timeout=timeout)

        return response

    async def enable_snap(
        self,
        snap: str,
        wait: bool = False,
        timeout: float | None = None,
    ) -> AsyncResponse | ChangesResponse:
        """
        enables a snap package.

        :param snap: The name of the snap package to enable.
        :type snap: str
        :param wait: Whether to wait for the enable operation to complete. Defaults to False.
        :type wait: bool, optional
        :param timeout: Maximum number of seconds to wait for the enable to finish, defaults to None (wait forever).
        :type timeout: float, optional

        :returns: The response from the enable operation.
        :rtype: AsyncResponse | ChangesResponse

        :raises SnapdAPIError: If there is an error during the snap enable operation.
        """
        request_data = {
            "action": "enable",
        }

        raw_response: httpx.Response = await self._client.request(
            "POST", f"{self.common_endpoint}/{snap}", json=request_data
        )
        response = AsyncResponse.model_validate_json(raw_response.content)

        if wait:
            return await self._wait_for_change(response.change, timeout=timeout)

        return response

    async def list_apps(
        self,
        names: list[str] | None = None,
        services_only: bool = False,
        global_scope: bool | None = None,
    ) -> AppsResponse:
        """
        Retrieves applications of the installed snaps.

        :param names: Snap names (all their apps are returned) or
            ``snap.app`` entries (that single app). snapd receives them as a
            comma-separated ``names`` query parameter. None (default) returns
            every app of the requested kind.
        :type names: list[str], optional
        :param services_only: Only return background daemons. snapd receives
            this as ``select=service``. Defaults to False.
        :type services_only: bool
        :param global_scope: For user services, report the global enable
            status instead of the status for the requesting user. None
            (default) omits the parameter; snapd always uses the global status
            for root.
        :type global_scope: bool, optional

        :returns: The response containing the matching applications.
        :rtype: AppsResponse

        :raises SnapdAPIError: If snapd rejects the request, for example when a
            name does not resolve to an app or the snap is not installed.
        """
        params: dict[str, Any] = {}
        if names:
            params["names"] = ",".join(names)
        if services_only:
            params["select"] = "service"
        if global_scope is not None:
            params["global"] = "true" if global_scope else "false"

        response: httpx.Response = await self._client.request(
            "GET", "apps", params=params
        )
        return AppsResponse.model_validate_json(response.content)

    async def get_snap_apps(
        self,
        snap: str,
        services_only: bool = False,
    ) -> AppsResponse:
        """
        Retrieves the applications associated with a specific snap.

        Thin wrapper around :meth:`list_apps` restricted to one snap.

        :param snap: The name of the snap to retrieve applications for.
        :type snap: str
        :param services_only: Whether to retrieve only service applications.
        :type services_only: bool

        :returns: The response containing the list of applications for the specified snap.
        :rtype: AppsResponse

        :raises SnapdAPIError: If snapd rejects the request.
        """
        return await self.list_apps(names=[snap], services_only=services_only)

    async def _post_app_action(
        self,
        action: str,
        names: list[str],
        *,
        reload: bool = False,
        wait: bool = False,
        timeout: float | None = None,
    ) -> AsyncResponse | ChangesResponse:
        """POST a service instruction to ``/v2/apps`` and optionally wait.

        :param action: ``"start"``, ``"stop"`` or ``"restart"``.
        :type action: str
        :param names: Snap names or ``snap.app`` names to operate on.
        :type names: list[str]
        :param reload: For ``"restart"``, ask snapd to reload the service when
            it has a reload command instead of restarting it. Defaults to
            False.
        :type reload: bool
        :param wait: Whether to wait for the resulting change.
        :type wait: bool
        :param timeout: Maximum number of seconds to wait, None waits forever.
        :type timeout: float, optional

        :returns: AsyncResponse, or ChangesResponse when ``wait`` is True.
        :rtype: AsyncResponse | ChangesResponse

        :raises SnapdAPIError: If snapd rejects the service instruction.
        """
        payload: dict[str, Any] = {"action": action, "names": names}
        if reload:
            payload["reload"] = True
        raw_response: httpx.Response = await self._client.request(
            "POST", "apps", json=payload
        )
        response = AsyncResponse.model_validate_json(raw_response.content)
        if wait:
            return await self._wait_for_change(response.change, timeout=timeout)
        return response

    async def start_apps(
        self,
        names: list[str],
        wait: bool = False,
        timeout: float | None = None,
    ) -> AsyncResponse | ChangesResponse:
        """
        Start the services of one or more snaps.

        ``POST /v2/apps`` with ``{"action": "start", "names": [...]}``. Each
        name may be a snap (all of its services are started) or ``snap.app``
        (only that service); snapd only operates on services and rejects an
        empty list with 400.

        :param names: Snap names or ``snap.app`` names to start. Must not be
            empty.
        :type names: list[str]
        :param wait: Whether to wait for the change to reach a terminal state.
            Defaults to False.
        :type wait: bool
        :param timeout: Maximum number of seconds to wait, defaults to None
            (wait forever).
        :type timeout: float, optional

        :returns: AsyncResponse, or ChangesResponse when ``wait`` is True.
        :rtype: AsyncResponse | ChangesResponse

        :raises SnapdAPIError: If snapd rejects the start, for example with
            kind ``snap-change-conflict`` when another change for the snap is
            in progress.
        """
        return await self._post_app_action("start", names, wait=wait, timeout=timeout)

    async def stop_apps(
        self,
        names: list[str],
        wait: bool = False,
        timeout: float | None = None,
    ) -> AsyncResponse | ChangesResponse:
        """
        Stop the services of one or more snaps.

        ``POST /v2/apps`` with ``{"action": "stop", "names": [...]}``. Each
        name may be a snap or ``snap.app``; snapd only operates on services
        and rejects an empty list with 400.

        :param names: Snap names or ``snap.app`` names to stop. Must not be
            empty.
        :type names: list[str]
        :param wait: Whether to wait for the change to reach a terminal state.
            Defaults to False.
        :type wait: bool
        :param timeout: Maximum number of seconds to wait, defaults to None
            (wait forever).
        :type timeout: float, optional

        :returns: AsyncResponse, or ChangesResponse when ``wait`` is True.
        :rtype: AsyncResponse | ChangesResponse

        :raises SnapdAPIError: If snapd rejects the stop.
        """
        return await self._post_app_action("stop", names, wait=wait, timeout=timeout)

    async def restart_apps(
        self,
        names: list[str],
        reload: bool = False,
        wait: bool = False,
        timeout: float | None = None,
    ) -> AsyncResponse | ChangesResponse:
        """
        Restart the services of one or more snaps.

        ``POST /v2/apps`` with ``{"action": "restart", "names": [...]}``.
        snapd has no separate ``reload`` action on this endpoint (its dispatch
        table is start/stop/restart); instead ``"reload": true`` asks it to run
        the service's reload command where one exists and to restart it
        otherwise.

        :param names: Snap names or ``snap.app`` names to restart. Must not be
            empty.
        :type names: list[str]
        :param reload: Send ``"reload": true`` so snapd reloads services that
            support it and restarts the rest. Defaults to False, which sends
            a plain restart.
        :type reload: bool
        :param wait: Whether to wait for the change to reach a terminal state.
            Defaults to False.
        :type wait: bool
        :param timeout: Maximum number of seconds to wait, defaults to None
            (wait forever).
        :type timeout: float, optional

        :returns: AsyncResponse, or ChangesResponse when ``wait`` is True.
        :rtype: AsyncResponse | ChangesResponse

        :raises SnapdAPIError: If snapd rejects the restart.
        """
        return await self._post_app_action(
            "restart", names, reload=reload, wait=wait, timeout=timeout
        )
