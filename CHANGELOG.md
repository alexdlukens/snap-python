# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

No changes yet.

## [0.2.0] - 2026-11-14

Published to PyPI on 2026-11-15. This release folds in the 0.1.8 work that was
version-bumped in-tree but never published, followed by a set of correctness
fixes and new API surface found by auditing the package against the Snap Store
and local snapd REST APIs.

### Added

- `SnapClient.changes` (`ChangeEndpoints`): `list_changes(select=, for_snap=)`,
  `get(change_id)`, `abort(change_id)` and `watch(change_id, timeout=,
  poll_interval=)`. `watch` yields each change until it is ready and raises
  `SnapdAPIError` on an error result or timeout. `SnapClient.get_changes_by_id`
  is kept as a delegate.
- `SnapClient.interfaces` (`InterfacesEndpoints`): `list_interfaces(select=,
  plugs=, slots=, doc=, names=)` (normalises snapd's legacy `{"plugs", "slots"}`
  and modern array response shapes), `connections(snap=, select=, interface=)`,
  `connect(plug_snap, plug_name, slot_snap=, slot_name=)` and
  `disconnect(..., forget=)`.
- `SnapClient.logs` (`LogsEndpoints`): `get_logs(names=, n=)` and
  `stream_logs(names=, n=)` over `/v2/logs`, parsing snapd's RFC 7464
  JSON-seq stream.
- Hold support: `hold_snap(snap, time=, hold_level=)`,
  `hold_snaps(snaps, time=, hold_level=)`, `hold_all_snaps(hold_level=)`, and
  the matching `unhold_snap`, `unhold_snaps` and `unhold_all_snaps`.
- Multi-snap operations: `install_snaps(snaps, transaction=,
  validation_sets=, quota_group=, ignore_running=)`,
  `refresh_snaps(snaps=, transaction=, validation_sets=, ignore_running=)`,
  `refresh_all_snaps(transaction=)` and
  `remove_snaps(snaps, purge=, terminate=)`.
- Revision and channel control: `revert_snap(snap, revision=)` and
  `switch_channel(snap, channel=, cohort_key=, leave_cohort=)`.
- Service control: `start_apps(names, wait=, timeout=)`,
  `stop_apps(names, wait=, timeout=)`,
  `restart_apps(names, reload=, wait=, timeout=)` and
  `list_apps(names=, services_only=, global_scope=)` via `POST /v2/apps`.
  `get_snap_apps` is retained.
- `list_installed_snaps(select=, snaps=)` so inactive revisions, selected snaps
  and refresh-inhibited snaps are reachable.
- `SnapClient.get_system_info()` for the `/v2/system-info` route.
- `InstalledSnap`/`InstalledSnapFields` now expose `hold`, `gating_hold`,
  `refresh_inhibit`, `refresh_failures`, `trymode`, `cohort_key`, `components`,
  `channels`, `tracks`, `grade` and `broken`.
- `SnapdAPIError.kind` and `SnapdAPIError.value`, carrying the parsed snapd
  error envelope so callers can branch on `snap-change-conflict`,
  `config-no-such-option`, `login-required`, and similar.
- `utils.async_retry`, an `asyncio`-native retry helper that retries only
  transient failures (transport/timeout errors, 429 and 5xx) and never
  non-idempotent methods.
- `SnapClient.close()`, `__aenter__`/`__aexit__`, and `is_available()`.
- `StoreEndpoints.close()`, `ChannelMapItem.supported_architectures` and
  `InfoResponse.supported_architectures`.
- `SnapTrackInfo` (renamed from `TrackRevisionDetails`) and `get_track_risk_map`
  support; `powerpc` added to the known architectures.

### Changed

- `SnapdAPIError` now subclasses `httpx.HTTPStatusError`, so existing
  `except httpx.HTTPStatusError` handlers and retry predicates keep working.
- `SnapClient` accepts `timeout` (default `60.0` seconds, or an `httpx.Timeout`)
  instead of inheriting httpx's 5-second default, which aborted large sideloads.
- `channel` no longer defaults to `"stable"` on install or refresh: `None` omits
  the parameter, so a refresh keeps the snap on its tracked channel instead of
  silently moving it to stable.
- Change waiters are shared: install/remove/refresh/disable/enable and
  `config.set_configuration` raise `SnapdAPIError` on failure or timeout instead
  of reporting success. The public methods take `wait` and `timeout`; the
  shared waiter also supports `poll_interval` and `progress_callback`.
- `get_snap_info` only treats HTTP 404 as "not installed"; other statuses raise
  `SnapdAPIError`. `get_installed_snap()` returns `None` only on 404, and
  `is_snap_installed()` builds on it.
- `ping()` raises on a non-2xx response.
- Store `find()` accepts `confinement` (previously misspelled `confiement`) and
  omits unset `featured`/`private` filters instead of sending them as `null`.
- Snap IDs are resolved through the configured store base URL; an unresolvable
  ID raises `ValueError` instead of requesting `/snaps/info/None`.
- `TrackRevisionDetails`/`SnapTrackInfo` no longer nests a `channel` field, and
  `base`/`version` are optional.
- The `retry` package dependency was dropped in favour of `utils.async_retry`.
- Default log level is `INFO`, overridable with `SNAP_PYTHON_LOG_LEVEL`.

### Fixed

- Store `find()` sends the documented hyphenated wire parameters
  `name-startswith` and `common-id`; the snake_case spellings previously made
  two filters return HTTP 400.
- Store requests omit the `fields` key entirely when no fields are requested;
  `"fields": null` returned HTTP 400.
- `Revision.base` accepts any base string (for example `core26`) through a
  before-validator; `SnapBaseVersion` is a plain `str` enum and unknown bases
  are no longer rejected.
- Sideloads no longer force the `dangerous` flag, and refresh-from-file sends
  `action=install` (the only multipart action snapd honours) instead of an
  ignored `action=refresh`. Snap file handles are now closed.
- `InstalledSnap` tolerates omitted `installed-size` and `mounted-from`, which
  snapd omits for installed-but-disabled snaps.
- Track risk maps no longer drop channel-map entries that lack an
  `architectures` field.
- `remove`/`refresh`/`install` failure results are surfaced instead of being
  treated as success.

## [0.1.7] - 2025-08-31

### Added

- Snap assertions are used to map snap IDs to names, allowing snap info to be
  retrieved by ID.

### Changed

- Loosened dependency constraints.
- Removed `extra="forbid"` from many schema models so unknown snapd/store
  fields no longer break validation.

## [0.1.6] - 2025-06-15

### Added

- Track risk map endpoint (`get_track_risk_map`) and the associated schemas;
  store documentation now covers the track module.

### Fixed

- `SnapClient.find` accepts `fields: list[str]`.
- Removed debug prints and a redundant `snapd_client` initialisation.

## [0.1.5] - 2025-05-25

### Added

- `disable_snap`, `enable_snap` and `get_snap_apps` routes.
- Schemas added to the Sphinx documentation.

### Fixed

- `installed-date` is absent exactly when the snap is installed and disabled.
- Docstring fixes for `get_snap_apps`.

## 0.1.x series (0.1.0 – 0.1.4)

### Added

- Initial published package (`0.1.0`, 2025-01-18): async `httpx` client for the
  snapd REST API and the Snap Store.
- Sphinx documentation published to GitHub Pages (`0.1.1`).
- Snap Store scrape module and `snap_refresh` store endpoint (`0.1.2`).
- Paginated search and store APIs, and a method to fetch many snap revisions at
  once (`0.1.4`).

### Fixed

- Kebab-case alias serialisation and re-validation for architecture searches
  (`0.1.2`).
- `RefreshResultData` error handling (`0.1.3`).

[Unreleased]: https://github.com/alexdlukens/snap-python/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/alexdlukens/snap-python/compare/v0.1.7...v0.2.0
[0.1.7]: https://github.com/alexdlukens/snap-python/compare/v0.1.6...v0.1.7
[0.1.6]: https://github.com/alexdlukens/snap-python/compare/v0.1.5...v0.1.6
[0.1.5]: https://github.com/alexdlukens/snap-python/compare/v0.1.4...v0.1.5
[0.1.4]: https://github.com/alexdlukens/snap-python/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/alexdlukens/snap-python/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/alexdlukens/snap-python/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/alexdlukens/snap-python/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/alexdlukens/snap-python/releases/tag/v0.1.0
