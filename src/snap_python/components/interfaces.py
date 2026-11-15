import logging
from typing import Any, Literal

from snap_python.schemas.changes import ChangesResponse
from snap_python.schemas.common import AsyncResponse
from snap_python.schemas.interfaces import (
    ConnectionsResponse,
    InterfaceActionPlug,
    InterfaceActionSlot,
    InterfacesResponse,
)
from snap_python.utils import AbstractSnapsClient, wait_for_change

logger = logging.getLogger("snap_python.components.interfaces")

#: Values ``GET /v2/interfaces`` accepts for ``select``. Sending no ``select``
#: at all selects the legacy object response shape.
InterfaceSelect = Literal["all", "connected"]

#: Values ``GET /v2/connections`` accepts for ``select``.
ConnectionsSelect = Literal["", "all"]


class InterfacesEndpoints:
    """Endpoints for interfaces and their connections.

    :param client: Client used to talk to snapd.
    """

    def __init__(self, client: AbstractSnapsClient) -> None:
        self._client = client
        self.common_endpoint = "interfaces"

    async def list_interfaces(
        self,
        select: InterfaceSelect | None = None,
        plugs: bool = False,
        slots: bool = False,
        doc: bool = False,
        names: list[str] | None = None,
    ) -> InterfacesResponse:
        """
        List interfaces known to snapd.

        snapd picks the response shape from ``select``: without it the legacy
        handler answers with a ``{"plugs": [...], "slots": [...]}`` object,
        with any non-empty value the modern handler answers with an array.
        :class:`InterfacesResponse` accepts both;
        :attr:`InterfacesResponse.legacy` tells them apart and
        :attr:`InterfacesResponse.interfaces` normalises them.

        The ``plugs``/``slots``/``doc`` flags are only honoured by the modern
        handler, and only when exactly ``true``; they are not sent unless
        requested.

        :param select: ``"all"`` or ``"connected"`` (the latter keeps only
            interfaces with at least one live connection). None (default)
            requests the legacy response shape.
        :type select: str, optional
        :param plugs: Include the ``plugs`` arrays. Only for the modern shape.
        :type plugs: bool
        :param slots: Include the ``slots`` arrays. Only for the modern shape.
        :type slots: bool
        :param doc: Include ``doc-url``, defaulting to
            ``https://snapcraft.io/docs/<name>-interface``. Only for the modern
            shape.
        :type doc: bool
        :param names: Restrict the result to these interface names. None
            (default) returns every interface. Names are joined with commas and
            snapd does not trim whitespace.
        :type names: list[str], optional

        :returns: The response object containing the interfaces.
        :rtype: InterfacesResponse

        :raises SnapdAPIError: If snapd rejects the request, for example for an
            unknown ``select`` value.
        :raises httpx.HTTPStatusError: If the request results in an HTTP error.
        """
        params: dict[str, str] = {}
        if select is not None:
            params["select"] = select
        if plugs:
            params["plugs"] = "true"
        if slots:
            params["slots"] = "true"
        if doc:
            params["doc"] = "true"
        if names:
            params["names"] = ",".join(names)

        response = await self._client.request(
            "GET", self.common_endpoint, params=params
        )
        return InterfacesResponse.model_validate_json(response.content)

    async def connections(
        self,
        snap: str | None = None,
        select: ConnectionsSelect | None = None,
        interface: str | None = None,
    ) -> ConnectionsResponse:
        """
        Retrieve plug/slot connections.

        :param snap: Only return connections involving this snap. snapd also
            keeps the counterpart plug/slot of another snap and everything
            connected to it. None (default) returns every snap. An unknown snap
            is a 404 ``snap-not-found``.
        :type snap: str, optional
        :param select: ``"all"`` also returns unconnected plugs/slots and
            undesired connections; ``""`` (daemon default when the parameter is
            omitted) returns only established connections. None (default) omits
            the parameter.
        :type select: str, optional
        :param interface: Only return connections, plugs and slots of this
            interface. An unknown interface yields an empty result.
        :type interface: str, optional

        :returns: The response object containing connections, plugs and slots.
        :rtype: ConnectionsResponse

        :raises SnapdAPIError: If snapd rejects the request, for example for an
            unknown ``select`` value or an unknown snap (404).
        :raises httpx.HTTPStatusError: If the request results in an HTTP error.
        """
        params: dict[str, str] = {}
        if snap is not None:
            params["snap"] = snap
        if select:
            params["select"] = select
        if interface is not None:
            params["interface"] = interface

        response = await self._client.request("GET", "connections", params=params)
        return ConnectionsResponse.model_validate_json(response.content)

    async def _change_interface(
        self,
        action: Literal["connect", "disconnect"],
        plug_snap: str,
        plug_name: str,
        slot_snap: str | None,
        slot_name: str | None,
        forget: bool,
        wait: bool,
        timeout: float | None,
        poll_interval: float,
    ) -> AsyncResponse | ChangesResponse:
        """POST one plug/slot pair to ``/v2/interfaces``.

        snapd rejects more than one plug or slot per request with 501
        ``many-to-many operations are not implemented``, so the API always
        sends exactly one of each. ``forget`` is only ever set by
        :meth:`disconnect`.
        """
        body: dict[str, Any] = {
            "action": action,
            "plugs": [InterfaceActionPlug(snap=plug_snap, plug=plug_name).model_dump()],
            "slots": [
                InterfaceActionSlot(
                    snap=slot_snap or "", slot=slot_name or ""
                ).model_dump()
            ],
        }
        if forget:
            body["forget"] = True

        response = await self._client.request("POST", self.common_endpoint, json=body)
        async_response = AsyncResponse.model_validate_json(response.content)
        if not wait:
            return async_response
        return await wait_for_change(
            self._client,
            async_response.change,
            timeout=timeout,
            poll_interval=poll_interval,
        )

    async def connect(
        self,
        plug_snap: str,
        plug_name: str,
        slot_snap: str | None = None,
        slot_name: str | None = None,
        wait: bool = True,
        timeout: float | None = None,
        poll_interval: float = 0.5,
    ) -> AsyncResponse | ChangesResponse:
        """
        Connect one plug to one slot.

        An empty ``slot_snap`` lets snapd fall back to ``snapd``, ``core`` or
        ``ubuntu-core``; an empty ``slot_name`` lets it pick the single slot of
        the plug's interface. Connecting an already connected pair still
        returns an async response, but with a change that is already done.

        :param plug_snap: Snap providing the plug.
        :type plug_snap: str
        :param plug_name: Name of the plug.
        :type plug_name: str
        :param slot_snap: Snap providing the slot, or None to let snapd choose.
        :type slot_snap: str, optional
        :param slot_name: Name of the slot, or None to let snapd choose.
        :type slot_name: str, optional
        :param wait: Wait for the connect change to finish before returning.
        :type wait: bool
        :param timeout: Maximum seconds to wait for the change when ``wait`` is
            True; None waits forever.
        :type timeout: float | None
        :param poll_interval: Seconds between two polls while waiting.
        :type poll_interval: float

        :returns: The async response, or the finished change when waiting.
        :rtype: AsyncResponse | ChangesResponse

        :raises SnapdAPIError: If snapd refuses the connection, or the change
            fails.
        :raises httpx.HTTPStatusError: If the request results in an HTTP error.
        """
        return await self._change_interface(
            "connect",
            plug_snap,
            plug_name,
            slot_snap,
            slot_name,
            forget=False,
            wait=wait,
            timeout=timeout,
            poll_interval=poll_interval,
        )

    async def disconnect(
        self,
        plug_snap: str,
        plug_name: str,
        slot_snap: str | None = None,
        slot_name: str | None = None,
        forget: bool = False,
        wait: bool = True,
        timeout: float | None = None,
        poll_interval: float = 0.5,
    ) -> AsyncResponse | ChangesResponse:
        """
        Disconnect one plug from one slot.

        :param plug_snap: Snap providing the plug.
        :type plug_snap: str
        :param plug_name: Name of the plug.
        :type plug_name: str
        :param slot_snap: Snap providing the slot, or None to let snapd choose.
        :type slot_snap: str, optional
        :param slot_name: Name of the slot, or None to let snapd choose.
        :type slot_name: str, optional
        :param forget: Drop the connection state instead of recording it as
            undesired, so a later refresh does not reconnect the pair.
        :type forget: bool
        :param wait: Wait for the disconnect change to finish before returning.
        :type wait: bool
        :param timeout: Maximum seconds to wait for the change when ``wait`` is
            True; None waits forever.
        :type timeout: float | None
        :param poll_interval: Seconds between two polls while waiting.
        :type poll_interval: float

        :returns: The async response, or the finished change when waiting.
        :rtype: AsyncResponse | ChangesResponse

        :raises SnapdAPIError: If snapd refuses the disconnection, for example
            because the pair is not connected, or the change fails.
        :raises httpx.HTTPStatusError: If the request results in an HTTP error.
        """
        return await self._change_interface(
            "disconnect",
            plug_snap,
            plug_name,
            slot_snap,
            slot_name,
            forget=forget,
            wait=wait,
            timeout=timeout,
            poll_interval=poll_interval,
        )
