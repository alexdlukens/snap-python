import logging
from typing import Optional

from pydantic import (
    AwareDatetime,
    BaseModel,
    field_validator,
)

from snap_python.schemas.store.info import Channel, ChannelMapItem

logger = logging.getLogger("snap_python.schemas.store.track")


class TrackRevisionDetails(BaseModel):
    arch: str
    base: str
    channel: Channel
    confinement: str
    created_at: AwareDatetime
    released_at: AwareDatetime
    revision: int
    risk: str
    track: str
    version: str

    @field_validator("arch")
    @classmethod
    def validate_arch(cls, value):
        valid_architectures = {
            "amd64",
            "arm64",
            "armhf",
            "i386",
            "ppc64el",
            "s390x",
            "riscv64",
        }
        if value not in valid_architectures:
            raise ValueError(
                f"Invalid architecture: {value}. Must be one of {', '.join(valid_architectures)}."
            )
        return value


class TrackRiskMap(BaseModel):
    amd64: Optional[TrackRevisionDetails] = None
    arm64: Optional[TrackRevisionDetails] = None
    armhf: Optional[TrackRevisionDetails] = None
    i386: Optional[TrackRevisionDetails] = None
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
    """Convert a list of ChannelMapItem to a map of TrackRiskMap.

    track -> risk -> arch
    """
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
            len(item.architectures) == 1
        ), "Channel must have exactly one architecture."

        assert (
            item.revision is not None
        ), f"Channel {item} must have a revision defined."
        assert item.channel is not None, f"Channel {item} must have a channel defined."
        assert item.base is not None, f"Channel {item} must have a base defined."
        assert (
            item.confinement is not None
        ), f"Channel {item} must have a confinement defined."
        assert item.version is not None, f"Channel {item} must have a version defined."
        assert (
            item.created_at is not None
        ), f"Channel {item} must have a created_at defined."
        assert (
            item.channel.released_at is not None
        ), f"Channel {item} must have a released_at defined."

        arch = item.architectures[0]

        revision_details = TrackRevisionDetails(
            arch=arch,
            base=item.base,
            channel=item.channel,
            confinement=item.confinement,
            created_at=item.created_at,
            released_at=item.channel.released_at,
            revision=item.revision,
            risk=risk,
            track=track,
            version=item.version,
        )

        if risk not in current_track_map[track]:
            current_track_map[track][risk] = TrackRiskMap()
        setattr(current_track_map[track][risk], arch, revision_details)

    # re validate the track map to ensure it has all required fields
    for track, risk_map in current_track_map.items():
        for risk in risk_map:
            risk_map[risk] = TrackRiskMap.model_validate(risk_map[risk])

    return current_track_map
