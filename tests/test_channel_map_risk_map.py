import pathlib

import pytest

from snap_python.schemas.store.info import InfoResponse
from snap_python.schemas.store.track import (
    TrackRevisionDetails,
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
            details: TrackRevisionDetails
            for arch, details in architectures.model_dump(exclude_none=True).items():
                details = TrackRevisionDetails.model_validate(details)
                assert details.arch == arch
                assert details.risk == risk
                assert details.track == track
                assert details.revision is not None
                assert details.version is not None
                assert details.base is not None
                assert details.confinement is not None
                assert details.created_at is not None
                assert details.released_at is not None
                assert details.channel is not None
