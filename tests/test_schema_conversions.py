# %%
import logging
from pathlib import Path

import pydantic

from snap_python.schemas.snaps import InstalledSnapListResponse
from snap_python.schemas.store.search import (
    SearchResponse,
    SearchResult,
)

BASE_DIR = Path(__file__).resolve().parent.parent
CODE_DIR = BASE_DIR / "src" / "snap_python"
TEST_DIR = BASE_DIR / "tests"
TEST_DATA_DIR = TEST_DIR / "data"

logger = logging.getLogger("snap_python.tests.test_schema_conversions")
logger.setLevel(logging.DEBUG)
logger.handlers.clear()
logger.propagate = True

INSTALLED_SNAP_RESPONSE_FILE = TEST_DATA_DIR / "installed_snaps_long.json"


def test_convert_store_snap():
    with open(INSTALLED_SNAP_RESPONSE_FILE, "r") as f:
        response = InstalledSnapListResponse.model_validate_json(f.read())
    assert len(response) > 0
    converted_snaps = []
    for snap in response.result:
        print(
            f"Name: {snap.name}, Version: {snap.version}, Publisher: {snap.publisher}"
        )

        try:
            converted_snaps.append(SearchResult.from_installed_snap(snap))
        except pydantic.ValidationError as e:
            print(f"Error converting snap {snap.name}: \n{e.json(indent=2)}")
            raise
    search_response = SearchResponse(results=converted_snaps)

    assert len(search_response.results) == len(response.result)