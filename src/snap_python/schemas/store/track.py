import logging
from typing import Optional

from pydantic import (
    AwareDatetime,
    BaseModel,
    field_validator,
)

from snap_python.schemas.common import VALID_SNAP_ARCHITECTURES
from snap_python.schemas.store.info import ChannelMapItem

logger = logging.getLogger("snap_python.schemas.store.track")


class TrackRevisionDetails(BaseModel):
    """Contains details for a specific track/risk/architecture


    Raises:
        ValueError: If the architecture is invalid.
    """

    name: str
    architecture: str
    base: str = "unset"
    confinement: str
    created_at: AwareDatetime
    released_at: AwareDatetime
    revision: int
    risk: str
    track: str
    version: str = "unset"

    @field_validator("architecture")
    @classmethod
    def validate_arch(cls, value):
        if value not in VALID_SNAP_ARCHITECTURES:
            raise ValueError(
                f"Invalid architecture: {value}. Must be one of {', '.join(VALID_SNAP_ARCHITECTURES)}."
            )
        return value


class TrackRiskMap(BaseModel):
    """Map of architectures to their revision details for a specific risk level."""

    amd64: Optional[TrackRevisionDetails] = None
    arm64: Optional[TrackRevisionDetails] = None
    armhf: Optional[TrackRevisionDetails] = None
    i386: Optional[TrackRevisionDetails] = None
    powerpc: Optional[TrackRevisionDetails] = None
    ppc64el: Optional[TrackRevisionDetails] = None
    s390x: Optional[TrackRevisionDetails] = None
    riscv64: Optional[TrackRevisionDetails] = None

    @property
    def architectures(self) -> list[str]:
        """Return a list of architectures that have revisions."""
        return [
            arch for arch, details in self.model_dump().items() if details is not None
        ]


def channel_map_to_current_track_map(
    channel_map: list[ChannelMapItem],
) -> dict[str, dict[str, TrackRiskMap]]:
    """Convert a list of ChannelMapItem to a map of track -> risk -> TrackRiskMap."""
    # track -> risk -> arch
    current_track_map: dict[str, dict[str, TrackRiskMap]] = {}

    all_tracks = set(item.channel.track for item in channel_map)
    logger.debug(f"Found tracks: {', '.join(all_tracks)}")

    for track in all_tracks:
        current_track_map[track] = {}

    for item in channel_map:
        track = item.channel.track
        risk = item.channel.risk

        if not item.architectures:
            logger.error(
                f"Warning: Channel {item} has no architectures defined. Skipping."
            )
            continue

        assert (
            item.revision is not None
        ), f"Channel {item} must have a revision defined."
        assert item.channel is not None, f"Channel {item} must have a channel defined."
        assert (
            item.confinement is not None
        ), f"Channel {item} must have a confinement defined."
        assert (
            item.created_at is not None
        ), f"Channel {item} must have a created_at defined."
        assert (
            item.channel.released_at is not None
        ), f"Channel {item} must have a released_at defined."

        if risk not in current_track_map[track]:
            # validated at end
            current_track_map[track][risk] = {}  # type: ignore

        current_track_map[track][risk][item.channel.architecture] = (
            TrackRevisionDetails(  # type: ignore
                name=item.channel.name,
                architecture=item.channel.architecture,
                base=item.base or "unset",
                confinement=item.confinement,
                created_at=item.created_at,
                released_at=item.channel.released_at,
                revision=item.revision,
                risk=risk,
                track=track,
                version=item.version or "unset",
            )
        )

    # re validate the track map to ensure it has all required fields
    for track, risk_map in current_track_map.items():
        for risk in risk_map:
            risk_map[risk] = TrackRiskMap.model_validate(risk_map[risk])

    return current_track_map


def channel_map_item_to_track_revision_details(
    item: ChannelMapItem,
) -> TrackRevisionDetails:
    """Convert a ChannelMapItem to a TrackRevisionDetails."""
    assert (
        item.revision is not None
    ), f"ChannelMapItem {item} must have a revision defined."
    assert (
        item.channel is not None
    ), f"ChannelMapItem {item} must have a channel defined."
    assert (
        item.channel.track is not None
    ), f"ChannelMapItem {item} must have a track defined."
    assert (
        item.channel.risk is not None
    ), f"ChannelMapItem {item} must have a risk defined."

    return TrackRevisionDetails(
        name=item.channel.name,
        architecture=item.channel.architecture,
        base=item.base or "unset",
        confinement=item.confinement or "unset",
        created_at=item.created_at,
        released_at=item.channel.released_at,
        revision=item.revision,
        risk=item.channel.risk,
        track=item.channel.track,
        version=item.version or "unset",
    )
