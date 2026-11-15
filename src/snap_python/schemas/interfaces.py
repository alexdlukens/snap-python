"""Models for ``/v2/interfaces`` and ``/v2/connections``.

snapd speaks two very different shapes for interfaces, discriminated on the
JSON type of the envelope ``result``:

* :class:`Interface` — a JSON array, returned by ``GET /v2/interfaces`` as
  soon as a non-empty ``select`` parameter is sent (the "modern" handler).
* :class:`LegacyConnections` — a JSON object, returned by
  ``GET /v2/interfaces`` when ``select`` is absent (the "legacy" handler).

:class:`Connections` is the object returned by ``GET /v2/connections``.
``plugs`` and ``slots`` entries in both connection shapes carry ``interface``,
``apps`` and ``connections``, which modern interface entries never do.
"""

from typing import Any

from pydantic import AliasChoices, BaseModel, Field

from snap_python.schemas.common import BaseErrorResult, BaseResponse


class PlugRef(BaseModel):
    """Reference to a plug: ``{"snap": "foo", "plug": "network"}``."""

    snap: str
    plug: str


class SlotRef(BaseModel):
    """Reference to a slot: ``{"snap": "core", "slot": "network"}``."""

    snap: str
    slot: str


class Connection(BaseModel):
    """One established or undesired connection between a plug and a slot."""

    slot: SlotRef
    plug: PlugRef
    interface: str
    #: ``manual`` and ``gadget`` are tagged ``omitempty`` in snapd, so a
    #: missing key means False.
    manual: bool = False
    gadget: bool = False
    slot_attrs: dict[str, Any] | None = Field(
        validation_alias=AliasChoices("slot-attrs", "slot_attrs"),
        serialization_alias="slot-attrs",
        default=None,
    )
    plug_attrs: dict[str, Any] | None = Field(
        validation_alias=AliasChoices("plug-attrs", "plug_attrs"),
        serialization_alias="plug-attrs",
        default=None,
    )


class Plug(BaseModel):
    """A plug as returned by ``/v2/connections`` and legacy ``/v2/interfaces``.

    :attr:`connections` lists the slots this plug is connected to.
    """

    snap: str
    plug: str
    interface: str | None = None
    attrs: dict[str, Any] | None = None
    apps: list[str] | None = None
    label: str | None = None
    connections: list[SlotRef] | None = None


class Slot(BaseModel):
    """A slot as returned by ``/v2/connections`` and legacy ``/v2/interfaces``.

    :attr:`connections` lists the plugs connected to this slot.
    """

    snap: str
    slot: str
    interface: str | None = None
    attrs: dict[str, Any] | None = None
    apps: list[str] | None = None
    label: str | None = None
    connections: list[PlugRef] | None = None


class Connections(BaseModel):
    """Result object of ``GET /v2/connections``."""

    established: list[Connection] = Field(default_factory=list)
    undesired: list[Connection] | None = None
    plugs: list[Plug] = Field(default_factory=list)
    slots: list[Slot] = Field(default_factory=list)


class ConnectionsResponse(BaseResponse):
    """Envelope of ``GET /v2/connections``."""

    result: Connections | BaseErrorResult

    @property
    def connections(self) -> Connections | None:
        """The connection information, or ``None`` for an error result."""
        if isinstance(self.result, BaseErrorResult):
            return None
        return self.result


class InterfacePlug(BaseModel):
    """A plug inside a modern ``/v2/interfaces`` entry.

    snapd only fills ``snap``, ``plug``, ``attrs`` and ``label`` here;
    ``interface``, ``apps`` and ``connections`` are never set.
    """

    snap: str
    plug: str
    attrs: dict[str, Any] | None = None
    label: str | None = None


class InterfaceSlot(BaseModel):
    """A slot inside a modern ``/v2/interfaces`` entry.

    snapd only fills ``snap``, ``slot``, ``attrs`` and ``label`` here.
    """

    snap: str
    slot: str
    attrs: dict[str, Any] | None = None
    label: str | None = None


class Interface(BaseModel):
    """One entry of the modern ``GET /v2/interfaces`` array.

    ``doc-url`` is only sent with ``doc=true``; ``plugs``/``slots`` are only
    sent, and only present when non-empty, with ``plugs=true``/``slots=true``.
    """

    name: str
    summary: str | None = None
    doc_url: str | None = Field(
        validation_alias=AliasChoices("doc-url", "doc_url"),
        serialization_alias="doc-url",
        default=None,
    )
    plugs: list[InterfacePlug] | None = None
    slots: list[InterfaceSlot] | None = None


class LegacyConnections(BaseModel):
    """Legacy ``GET /v2/interfaces`` result: ``{"plugs": [...], "slots": [...]}``.

    Both keys are ``omitempty``; there is no ``established`` key.
    """

    plugs: list[Plug] | None = None
    slots: list[Slot] | None = None


class InterfaceSummary(BaseModel):
    """Shape-independent view of one interface.

    Built from either response shape by
    :attr:`InterfacesResponse.interfaces`. Only references are exposed:
    ``attrs``/``apps``/``label`` stay available on the raw models.
    """

    name: str
    summary: str | None = None
    doc_url: str | None = None
    plugs: list[PlugRef] = Field(default_factory=list)
    slots: list[SlotRef] = Field(default_factory=list)


class InterfacesResponse(BaseResponse):
    """Envelope of ``GET /v2/interfaces``, accepting both response shapes.

    Use :attr:`legacy` to tell which shape snapd answered with and
    :attr:`interfaces` for a normalised view.
    """

    result: list[Interface] | LegacyConnections | BaseErrorResult

    @property
    def legacy(self) -> bool:
        """True when snapd answered with the legacy object shape."""
        return isinstance(self.result, LegacyConnections)

    @property
    def interfaces(self) -> list[InterfaceSummary]:
        """Normalised, name-sorted view of either response shape."""
        if isinstance(self.result, BaseErrorResult):
            return []
        if isinstance(self.result, list):
            return [
                InterfaceSummary(
                    name=interface.name,
                    summary=interface.summary,
                    doc_url=interface.doc_url,
                    plugs=[
                        PlugRef(snap=plug.snap, plug=plug.plug)
                        for plug in interface.plugs or []
                    ],
                    slots=[
                        SlotRef(snap=slot.snap, slot=slot.slot)
                        for slot in interface.slots or []
                    ],
                )
                for interface in self.result
            ]

        summaries: dict[str, InterfaceSummary] = {}
        for plug in self.result.plugs or []:
            # Legacy entries should always carry the interface name; use an
            # empty name rather than dropping information when they do not.
            summary = summaries.setdefault(
                plug.interface or "",
                InterfaceSummary(name=plug.interface or ""),
            )
            summary.plugs.append(PlugRef(snap=plug.snap, plug=plug.plug))
        for slot in self.result.slots or []:
            summary = summaries.setdefault(
                slot.interface or "",
                InterfaceSummary(name=slot.interface or ""),
            )
            summary.slots.append(SlotRef(snap=slot.snap, slot=slot.slot))
        return [summaries[name] for name in sorted(summaries)]


class InterfaceActionPlug(BaseModel):
    """Plug item accepted by ``POST /v2/interfaces``.

    snapd reads only ``snap`` and ``plug``; every other field is ignored.
    """

    snap: str
    plug: str


class InterfaceActionSlot(BaseModel):
    """Slot item accepted by ``POST /v2/interfaces``.

    snapd reads only ``snap`` and ``slot``; every other field is ignored.
    """

    snap: str
    slot: str
