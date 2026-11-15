"""Offline tests for the P1 snapd operations (hold, multi-snap, revert,
switch, filtered listing and app lifecycle).

Every request is served by an ``httpx.MockTransport``; no snapd socket and no
network are involved. The assertions mirror what snapd's daemon accepts:

* ``daemon/api_snaps.go`` (action dispatch, accepted JSON fields, query
  parameters)
* ``daemon/api_apps.go`` plus ``overlord/servicestate`` (service instructions)
"""

import json

import httpx
import pytest

from snap_python.client import SnapClient
from snap_python.schemas.changes import ChangesResponse
from snap_python.schemas.common import AsyncResponse
from snap_python.utils import SnapdAPIError

ASYNC_ACCEPTED = {
    "status-code": 202,
    "type": "async",
    "status": "Accepted",
    "change": "1",
}

READY_CHANGE = {
    "status-code": 200,
    "type": "async",
    "status": "Done",
    "result": {
        "id": "1",
        "kind": "hold-snap",
        "summary": 'Hold general refreshes for "hello-world"',
        "status": "Done",
        "tasks": [],
        "ready": True,
        "spawn-time": "2024-01-01T00:00:00+00:00",
    },
}


def make_client(handler) -> SnapClient:
    """Build a SnapClient whose snapd transport is a MockTransport."""
    client = SnapClient(version="v2")
    client.snapd_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client


def capture(handler=None):
    """Return a MockTransport handler recording the request it served."""
    captured: dict = {}

    def recording_handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        if handler is not None:
            return handler(request)
        return httpx.Response(202, json=ASYNC_ACCEPTED)

    return captured, recording_handler


def sent_body(captured: dict) -> dict:
    return json.loads(captured["request"].content)


# --- ITEM 16: filterable installed-snap listing --------------------------


@pytest.mark.asyncio
async def test_list_installed_snaps_omits_filters_by_default():
    captured, handler = capture(
        lambda request: httpx.Response(
            200,
            json={"status-code": 200, "type": "sync", "status": "OK", "result": []},
        )
    )
    client = make_client(handler)

    await client.snaps.list_installed_snaps()

    request = captured["request"]
    assert request.method == "GET"
    assert request.url.path == "/v2/snaps"
    assert dict(request.url.params) == {}


@pytest.mark.asyncio
async def test_list_installed_snaps_passes_select_all():
    captured, handler = capture(
        lambda request: httpx.Response(
            200,
            json={"status-code": 200, "type": "sync", "status": "OK", "result": []},
        )
    )
    client = make_client(handler)

    await client.snaps.list_installed_snaps(select="all")

    assert dict(captured["request"].url.params) == {"select": "all"}


@pytest.mark.asyncio
async def test_list_installed_snaps_passes_refresh_inhibited_select():
    captured, handler = capture(
        lambda request: httpx.Response(
            200,
            json={"status-code": 200, "type": "sync", "status": "OK", "result": []},
        )
    )
    client = make_client(handler)

    await client.snaps.list_installed_snaps(select="refresh-inhibited")

    assert dict(captured["request"].url.params) == {"select": "refresh-inhibited"}


@pytest.mark.asyncio
async def test_list_installed_snaps_joins_snaps_with_commas():
    captured, handler = capture(
        lambda request: httpx.Response(
            200,
            json={"status-code": 200, "type": "sync", "status": "OK", "result": []},
        )
    )
    client = make_client(handler)

    await client.snaps.list_installed_snaps(snaps=["hello-world", "core22"])

    assert dict(captured["request"].url.params) == {"snaps": "hello-world,core22"}


# --- ITEM 9: hold / unhold ----------------------------------------------


@pytest.mark.asyncio
async def test_hold_snap_sends_forever_and_general_by_default():
    captured, handler = capture()
    client = make_client(handler)

    response = await client.snaps.hold_snap("hello-world")

    assert isinstance(response, AsyncResponse)
    assert captured["request"].url.path == "/v2/snaps/hello-world"
    assert sent_body(captured) == {
        "action": "hold",
        "time": "forever",
        "hold-level": "general",
    }


@pytest.mark.asyncio
async def test_hold_snap_sends_custom_time_and_level():
    captured, handler = capture()
    client = make_client(handler)

    await client.snaps.hold_snap(
        "hello-world",
        time="2026-01-01T00:00:00Z",
        hold_level="auto-refresh",
    )

    assert sent_body(captured) == {
        "action": "hold",
        "time": "2026-01-01T00:00:00Z",
        "hold-level": "auto-refresh",
    }


@pytest.mark.asyncio
async def test_unhold_snap_sends_only_the_action():
    captured, handler = capture()
    client = make_client(handler)

    await client.snaps.unhold_snap("hello-world")

    assert captured["request"].url.path == "/v2/snaps/hello-world"
    assert sent_body(captured) == {"action": "unhold"}


@pytest.mark.asyncio
async def test_hold_all_snaps_omits_snaps_and_defaults_to_auto_refresh():
    captured, handler = capture()
    client = make_client(handler)

    await client.snaps.hold_all_snaps()

    # snapd only supports the system-wide hold as an auto-refresh
    # ``refresh.hold`` change on core, with no ``snaps`` field.
    assert captured["request"].url.path == "/v2/snaps"
    assert sent_body(captured) == {
        "action": "hold",
        "time": "forever",
        "hold-level": "auto-refresh",
    }


@pytest.mark.asyncio
async def test_unhold_all_snaps_sends_only_the_action():
    captured, handler = capture()
    client = make_client(handler)

    await client.snaps.unhold_all_snaps()

    assert captured["request"].url.path == "/v2/snaps"
    assert sent_body(captured) == {"action": "unhold"}


@pytest.mark.asyncio
async def test_hold_snaps_sends_multi_body():
    captured, handler = capture()
    client = make_client(handler)

    await client.snaps.hold_snaps(
        ["hello-world", "core22"], time="2026-01-01T00:00:00Z"
    )

    assert sent_body(captured) == {
        "action": "hold",
        "snaps": ["hello-world", "core22"],
        "time": "2026-01-01T00:00:00Z",
        "hold-level": "general",
    }


@pytest.mark.asyncio
async def test_unhold_snaps_omits_time_and_hold_level():
    captured, handler = capture()
    client = make_client(handler)

    await client.snaps.unhold_snaps(["hello-world", "core22"])

    assert sent_body(captured) == {
        "action": "unhold",
        "snaps": ["hello-world", "core22"],
    }


@pytest.mark.asyncio
async def test_hold_all_snaps_surfaces_daemon_rejection():
    daemon_rejection = {
        "status-code": 400,
        "type": "error",
        "status": "Bad Request",
        "result": {
            "message": "holding general refreshes for all snaps is not supported",
            "kind": "bad-request",
        },
    }
    captured, handler = capture(
        lambda request: httpx.Response(400, json=daemon_rejection)
    )
    client = make_client(handler)

    with pytest.raises(SnapdAPIError) as excinfo:
        await client.snaps.hold_all_snaps(hold_level="general")

    assert excinfo.value.kind == "bad-request"
    assert "holding general refreshes" in str(excinfo.value)
    # The rejected value is sent verbatim; the client does not swallow it.
    assert sent_body(captured)["hold-level"] == "general"


# --- ITEM 12: multi-snap JSON operations --------------------------------


@pytest.mark.asyncio
async def test_install_snaps_sends_full_multi_body():
    captured, handler = capture()
    client = make_client(handler)

    await client.snaps.install_snaps(
        ["hello-world", "core22"],
        transaction="all-snaps",
        validation_sets=["acme/set"],
        quota_group="group-1",
        ignore_running=True,
    )

    assert captured["request"].url.path == "/v2/snaps"
    assert sent_body(captured) == {
        "action": "install",
        "snaps": ["hello-world", "core22"],
        "transaction": "all-snaps",
        "validation-sets": ["acme/set"],
        "quota-group": "group-1",
        "ignore-running": True,
    }


@pytest.mark.asyncio
async def test_install_snaps_omits_unset_options():
    captured, handler = capture()
    client = make_client(handler)

    await client.snaps.install_snaps(["hello-world"])

    assert sent_body(captured) == {"action": "install", "snaps": ["hello-world"]}


@pytest.mark.asyncio
async def test_refresh_snaps_sends_names_and_transaction():
    captured, handler = capture()
    client = make_client(handler)

    await client.snaps.refresh_snaps(["hello-world", "core22"], transaction="per-snap")

    assert sent_body(captured) == {
        "action": "refresh",
        "snaps": ["hello-world", "core22"],
        "transaction": "per-snap",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("snaps", [None, []])
async def test_refresh_snaps_without_names_refreshes_all(snaps):
    captured, handler = capture()
    client = make_client(handler)

    await client.snaps.refresh_snaps(snaps)

    # An omitted ``snaps`` field is snapd's "refresh every installed snap".
    assert sent_body(captured) == {"action": "refresh"}


@pytest.mark.asyncio
async def test_refresh_all_snaps_is_a_full_refresh():
    captured, handler = capture()
    client = make_client(handler)

    await client.snaps.refresh_all_snaps()

    assert captured["request"].url.path == "/v2/snaps"
    assert sent_body(captured) == {"action": "refresh"}


@pytest.mark.asyncio
async def test_refresh_snaps_sends_validation_sets_without_names():
    captured, handler = capture()
    client = make_client(handler)

    await client.snaps.refresh_snaps(validation_sets=["acme/set=42"])

    assert sent_body(captured) == {
        "action": "refresh",
        "validation-sets": ["acme/set=42"],
    }


@pytest.mark.asyncio
async def test_remove_snaps_sends_purge_only_when_requested():
    captured, handler = capture()
    client = make_client(handler)

    await client.snaps.remove_snaps(["hello-world"])

    assert sent_body(captured) == {"action": "remove", "snaps": ["hello-world"]}


@pytest.mark.asyncio
async def test_remove_snaps_sends_purge_and_terminate():
    captured, handler = capture()
    client = make_client(handler)

    await client.snaps.remove_snaps(
        ["hello-world", "core22"], purge=True, terminate=True
    )

    assert sent_body(captured) == {
        "action": "remove",
        "snaps": ["hello-world", "core22"],
        "purge": True,
        "terminate": True,
    }


# --- ITEM 13: revert and switch -----------------------------------------


@pytest.mark.asyncio
async def test_revert_snap_defaults_to_previous_revision():
    captured, handler = capture()
    client = make_client(handler)

    await client.snaps.revert_snap("hello-world")

    assert captured["request"].url.path == "/v2/snaps/hello-world"
    assert sent_body(captured) == {"action": "revert"}


@pytest.mark.asyncio
async def test_revert_snap_sends_revision():
    captured, handler = capture()
    client = make_client(handler)

    await client.snaps.revert_snap("hello-world", revision=41)

    assert sent_body(captured) == {"action": "revert", "revision": 41}


@pytest.mark.asyncio
async def test_switch_channel_sends_channel_only():
    captured, handler = capture()
    client = make_client(handler)

    await client.snaps.switch_channel("hello-world", "latest/edge")

    assert captured["request"].url.path == "/v2/snaps/hello-world"
    assert sent_body(captured) == {"action": "switch", "channel": "latest/edge"}


@pytest.mark.asyncio
async def test_switch_channel_sends_cohort_key():
    captured, handler = capture()
    client = make_client(handler)

    await client.snaps.switch_channel(
        "hello-world", "latest/edge", cohort_key="cohort-1"
    )

    assert sent_body(captured) == {
        "action": "switch",
        "channel": "latest/edge",
        "cohort-key": "cohort-1",
    }


@pytest.mark.asyncio
async def test_switch_channel_leave_cohort_without_channel():
    captured, handler = capture()
    client = make_client(handler)

    await client.snaps.switch_channel("hello-world", leave_cohort=True)

    # snapd keeps the tracking channel when ``channel`` is absent and only
    # clears the cohort.
    assert sent_body(captured) == {"action": "switch", "leave-cohort": True}


# --- ITEM 14: app/service lifecycle -------------------------------------


@pytest.mark.asyncio
async def test_start_apps_sends_names():
    captured, handler = capture()
    client = make_client(handler)

    response = await client.snaps.start_apps(["lxd", "lxd.daemon"])

    assert isinstance(response, AsyncResponse)
    assert captured["request"].url.path == "/v2/apps"
    assert sent_body(captured) == {
        "action": "start",
        "names": ["lxd", "lxd.daemon"],
    }


@pytest.mark.asyncio
async def test_stop_apps_sends_names():
    captured, handler = capture()
    client = make_client(handler)

    await client.snaps.stop_apps(["lxd"])

    assert sent_body(captured) == {"action": "stop", "names": ["lxd"]}


@pytest.mark.asyncio
async def test_restart_apps_omits_reload_by_default():
    captured, handler = capture()
    client = make_client(handler)

    await client.snaps.restart_apps(["lxd"])

    assert sent_body(captured) == {"action": "restart", "names": ["lxd"]}


@pytest.mark.asyncio
async def test_restart_apps_sends_reload():
    captured, handler = capture()
    client = make_client(handler)

    await client.snaps.restart_apps(["lxd"], reload=True)

    # snapd has no "reload" action on /v2/apps; "reload": true makes the
    # restart reload the service when it supports it.
    assert sent_body(captured) == {
        "action": "restart",
        "names": ["lxd"],
        "reload": True,
    }


def apps_payload():
    return {
        "status-code": 200,
        "type": "sync",
        "status": "OK",
        "result": [
            {
                "snap": "lxd",
                "name": "daemon",
                "daemon": "simple",
                "daemon-scope": "system",
                "enabled": True,
                "active": True,
            }
        ],
    }


@pytest.mark.asyncio
async def test_list_apps_joins_names_and_selects_services():
    captured, handler = capture(
        lambda request: httpx.Response(200, json=apps_payload())
    )
    client = make_client(handler)

    response = await client.snaps.list_apps(
        names=["lxd", "lxd.daemon"], services_only=True, global_scope=False
    )

    assert captured["request"].url.path == "/v2/apps"
    assert dict(captured["request"].url.params) == {
        "names": "lxd,lxd.daemon",
        "select": "service",
        "global": "false",
    }
    assert response.result[0].daemon_scope == "system"


@pytest.mark.asyncio
async def test_list_apps_omits_query_when_unfiltered():
    captured, handler = capture(
        lambda request: httpx.Response(200, json=apps_payload())
    )
    client = make_client(handler)

    await client.snaps.list_apps()

    assert dict(captured["request"].url.params) == {}


@pytest.mark.asyncio
async def test_get_snap_apps_still_queries_one_snap():
    captured, handler = capture(
        lambda request: httpx.Response(200, json=apps_payload())
    )
    client = make_client(handler)

    await client.snaps.get_snap_apps("lxd")

    assert dict(captured["request"].url.params) == {"names": "lxd"}


# --- waiting on the change ------------------------------------------------


@pytest.mark.asyncio
async def test_multi_snap_action_waits_for_change():
    captured: dict = {"paths": []}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["paths"].append(request.url.path)
        if request.url.path == "/v2/changes/1":
            return httpx.Response(200, json=READY_CHANGE)
        return httpx.Response(202, json=ASYNC_ACCEPTED)

    client = make_client(handler)

    response = await client.snaps.refresh_all_snaps(wait=True)

    assert isinstance(response, ChangesResponse)
    assert response.ready
    assert captured["paths"] == ["/v2/snaps", "/v2/changes/1"]
