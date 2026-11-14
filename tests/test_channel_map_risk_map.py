import pathlib

import pytest

from snap_python.schemas.store.info import InfoResponse
from snap_python.schemas.store.track import (
    SnapTrackInfo,
    TrackRiskMap,
    channel_map_to_current_track_map,
)

TEST_DIR = pathlib.Path(__file__).parent
DATA_DIR = TEST_DIR / "data"
CONVERTERMULTI_JSON = DATA_DIR / "convertermulti_info_response.json"


@pytest.mark.asyncio
async def test_get_categories_success():
    with open(CONVERTERMULTI_JSON) as f:
        info_response = InfoResponse.model_validate_json(f.read())

    track_map: dict[str, dict[str, TrackRiskMap]] = channel_map_to_current_track_map(
        info_response.channel_map
    )

    for track, risks in track_map.items():
        for risk, architectures in risks.items():
            details: SnapTrackInfo
            for arch, details in architectures.model_dump(exclude_none=True).items():
                details = SnapTrackInfo.model_validate(details)
                assert details.architecture == arch
                assert details.risk == risk
                assert details.track == track
                assert details.revision is not None
                assert details.version is not None
                assert details.base is not None
                assert details.confinement is not None
                assert details.created_at is not None
                assert details.released_at is not None
                assert details.name is not None


def load_info_response(name: str) -> InfoResponse:
    with open(DATA_DIR / name) as f:
        return InfoResponse.model_validate_json(f.read())


def test_supported_architectures_without_per_entry_architectures():
    # live /v2/snaps/info responses omit "architectures" on channel-map items
    info = load_info_response("snap_info_response_success.json")
    assert all(item.architectures is None for item in info.channel_map)

    for item in info.channel_map:
        assert item.supported_architectures == [item.channel.architecture]

    expected = sorted({item.channel.architecture for item in info.channel_map})
    assert info.supported_architectures == expected
    assert info.supported_architectures  # union is not empty


def test_supported_architectures_with_per_entry_architectures():
    info = load_info_response("store_tui_info_response.json")
    assert info.supported_architectures == sorted({"amd64", "arm64", "armhf"})


def test_channel_map_to_current_track_map_without_per_entry_architectures():
    info = load_info_response("snap_info_response_success.json")

    track_map = channel_map_to_current_track_map(info.channel_map)

    assert set(track_map.keys()) == {"latest"}
    assert track_map["latest"], "channel map conversion must not be empty"

    expected_arches = {item.channel.architecture for item in info.channel_map}
    for risk_map in track_map["latest"].values():
        assert set(risk_map.architectures) == expected_arches
        for arch in risk_map.architectures:
            details = getattr(risk_map, arch)
            assert details.architecture == arch
            assert details.revision is not None
