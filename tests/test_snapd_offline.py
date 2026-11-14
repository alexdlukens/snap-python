import json
from pathlib import Path

import httpx
import pytest

from snap_python.client import SnapClient
from snap_python.schemas.snaps import InstalledSnapListResponse
from snap_python.schemas.store.search import SearchResponse

ASYNC_ACCEPTED = {
    "status-code": 202,
    "type": "async",
    "status": "Accepted",
    "change": "1",
}


def make_client(handler) -> SnapClient:
    """Build a SnapClient whose snapd transport is a MockTransport."""
    client = SnapClient(version="v2")
    client.snapd_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client


def capture_response(captured: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(202, json=ASYNC_ACCEPTED)

    return handler


# --- P0-5: channel is omitted when not requested -------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("method_name", ["install_snap", "refresh_snap"])
async def test_snap_action_omits_channel_by_default(method_name: str):
    captured: dict = {}
    client = make_client(capture_response(captured))

    await getattr(client.snaps, method_name)("hello-world")

    body = json.loads(captured["request"].content)
    assert "channel" not in body


@pytest.mark.asyncio
@pytest.mark.parametrize("method_name", ["install_snap", "refresh_snap"])
async def test_snap_action_sends_explicit_channel(method_name: str):
    captured: dict = {}
    client = make_client(capture_response(captured))

    await getattr(client.snaps, method_name)("hello-world", channel="latest/edge")

    body = json.loads(captured["request"].content)
    assert body["channel"] == "latest/edge"


# --- P0-7: sideload semantics --------------------------------------------


def _write_snap(tmp_path: Path) -> Path:
    snap_path = tmp_path / "store-tui_29.snap"
    snap_path.write_bytes(b"not a real snap, but snapd is mocked")
    return snap_path


def _form_field(body: bytes, name: str) -> bytes | None:
    """Return the raw value of a multipart form field, if present."""
    marker = f'name="{name}"'.encode()
    index = body.find(marker)
    if index == -1:
        return None
    value_start = body.find(b"\r\n\r\n", index) + 4
    value_end = body.find(b"\r\n", value_start)
    return body[value_start:value_end]


@pytest.mark.asyncio
async def test_install_sideload_does_not_inject_dangerous(tmp_path: Path):
    captured: dict = {}
    client = make_client(capture_response(captured))
    snap_file = _write_snap(tmp_path)

    await client.snaps.install_snap("store-tui", filename=str(snap_file))

    request = captured["request"]
    body = request.content
    assert _form_field(body, "action") == b"install"
    assert _form_field(body, "snap-path") == str(snap_file).encode()
    assert _form_field(body, "dangerous") is None
    assert b'filename="store-tui_29.snap"' in body


@pytest.mark.asyncio
async def test_refresh_sideload_uses_install_action_and_honors_channel(
    tmp_path: Path,
):
    captured: dict = {}
    client = make_client(capture_response(captured))
    snap_file = _write_snap(tmp_path)

    await client.snaps.refresh_snap(
        "store-tui", filename=str(snap_file), channel="latest/edge"
    )

    body = captured["request"].content
    # snapd's multipart handler ignores any action other than "try"; the
    # refresh of a local file is a path install.
    assert _form_field(body, "action") == b"install"
    assert _form_field(body, "channel") == b"latest/edge"
    assert _form_field(body, "dangerous") is None


@pytest.mark.asyncio
async def test_sideload_passes_dangerous_through_when_requested(tmp_path: Path):
    captured: dict = {}
    client = make_client(capture_response(captured))
    snap_file = _write_snap(tmp_path)

    await client.snaps.install_snap(
        "store-tui", filename=str(snap_file), dangerous=True
    )

    body = captured["request"].content
    assert _form_field(body, "dangerous") == b"true"


@pytest.mark.asyncio
async def test_sideload_closes_the_snap_file(tmp_path: Path, monkeypatch):
    import snap_python.components.snaps as snaps_module

    captured: dict = {}
    client = make_client(capture_response(captured))
    snap_file = _write_snap(tmp_path)

    opened: list = []
    real_open = open

    def tracking_open(*args, **kwargs):
        handle = real_open(*args, **kwargs)
        opened.append(handle)
        return handle

    monkeypatch.setattr(snaps_module, "open", tracking_open, raising=False)

    await client.snaps.install_snap("store-tui", filename=str(snap_file))

    assert opened, "the snap file should have been opened"
    assert all(handle.closed for handle in opened)


# --- P0-8: snapd client timeout ------------------------------------------


def test_client_timeout_is_configurable():
    client = SnapClient(version="v2", timeout=120)
    assert client.snapd_client.timeout == httpx.Timeout(120)


def test_client_default_timeout_is_60_seconds():
    client = SnapClient(version="v2")
    assert client.snapd_client.timeout == httpx.Timeout(60.0)


def test_client_timeout_none_disables_timeouts():
    client = SnapClient(version="v2", timeout=None)
    assert client.snapd_client.timeout.connect is None
    assert client.snapd_client.timeout.read is None
    assert client.snapd_client.timeout.write is None


# --- P0-2: unknown base versions are forward compatible ------------------


def test_search_response_accepts_core26_and_unknown_base_versions():
    payload = {
        "results": [
            {
                "name": "krita",
                "snap-id": "krita-snap-id",
                "snap": {"name": "krita"},
                "revision": {
                    "base": "core26",
                    "channel": "latest/stable",
                    "confinement": "strict",
                    "revision": 123,
                    "version": "6.0",
                },
            },
            {
                "name": "future-snap",
                "snap-id": "future-snap-id",
                "snap": {"name": "future-snap"},
                "revision": {"base": "core28"},
            },
        ]
    }

    response = SearchResponse.model_validate(payload)

    assert [result.revision.base for result in response.results] == [
        "core26",
        "core28",
    ]


# --- P0-6: InstalledSnap is lenient and lossless -------------------------


def test_trymode_snap_without_installed_size_or_mounted_from_parses():
    payload = {
        "status-code": 200,
        "type": "sync",
        "status": "OK",
        "result": [
            {
                "name": "try-snap",
                "revision": "x1",
                "status": "active",
                "type": "app",
                "trymode": True,
                "jailmode": False,
                "ignore-validation": False,
            }
        ],
    }

    response = InstalledSnapListResponse.model_validate(payload)
    snap = response.result[0]

    assert snap.trymode is True
    assert snap.installed_size is None
    assert snap.mounted_from is None


def test_held_snap_exposes_hold_and_refresh_fields():
    payload = {
        "status-code": 200,
        "type": "sync",
        "status": "OK",
        "result": [
            {
                "name": "held-snap",
                "revision": "42",
                "status": "active",
                "type": "app",
                "base": "core22",
                "grade": "stable",
                "jailmode": False,
                "ignore-validation": False,
                "installed-size": 4096,
                "mounted-from": "/var/lib/snapd/snaps/held-snap_42.snap",
                "hold": "2026-01-01T00:00:00Z",
                "gating-hold": "2026-02-01T00:00:00Z",
                "refresh-inhibit": {"proceed-time": "2026-03-01T00:00:00Z"},
                "refresh-failures": {
                    "revision": "43",
                    "failure-count": 2,
                    "last-failure-time": "2026-01-05T00:00:00Z",
                    "last-failure-severity": "retry",
                },
                "cohort-key": "cohort-1",
                "broken": "",
                "tracks": ["latest"],
                "components": [
                    {
                        "name": "translations",
                        "type": "test",
                        "version": "1.0",
                        "revision": "7",
                        "installed-size": 128,
                    }
                ],
                "channels": {
                    "latest/stable": {
                        "revision": "42",
                        "confinement": "strict",
                        "version": "1.0",
                        "channel": "latest/stable",
                        "size": 4096,
                        "released-at": "2025-12-01T00:00:00Z",
                    }
                },
            }
        ],
    }

    response = InstalledSnapListResponse.model_validate(payload)
    snap = response.result[0]

    assert snap.hold is not None and snap.hold.year == 2026
    assert snap.gating_hold is not None and snap.gating_hold.month == 2
    assert snap.refresh_inhibit is not None
    assert snap.refresh_inhibit.proceed_time.month == 3
    assert snap.refresh_failures is not None
    assert snap.refresh_failures.failure_count == 2
    assert snap.refresh_failures.last_failure_severity == "retry"
    assert snap.cohort_key == "cohort-1"
    assert snap.grade == "stable"
    assert snap.tracks == ["latest"]
    assert snap.components[0].name == "translations"
    assert snap.channels["latest/stable"].size == 4096
