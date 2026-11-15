# snap-python

snap-python provides an async API client to interact with snapd, the Snap Store, and snaps installed on the local machine

[Click here to read the documentation](https://alexdlukens.github.io/snap-python/)

## Installation

To install snap-python, you can use pip:

```
pip install snap-python
```

## Quickstart

List the snaps installed on the local machine:

```python
import asyncio

from snap_python.client import SnapClient


async def main() -> None:
    async with SnapClient() as client:
        response = await client.snaps.list_installed_snaps()
        for snap in response.result:
            # e.g. "firefox 128.0 stable"
            print(snap.name, snap.version, snap.tracking_channel)


asyncio.run(main())
```

Reading state needs no root privileges. `SnapClient` also exposes:

- `client.snaps` — list, inspect, install, refresh, remove, hold, revert and switch channel on installed snaps, plus app control
- `client.config` — read and write a snap's configuration
- `client.store` — search the Snap Store, list categories, inspect store-side snap details
- `client.changes` — list, inspect, abort and watch changes
- `client.interfaces` — list interfaces and connections, connect or disconnect them
- `client.logs` — read a bounded batch of service logs, or stream them as they are written

`client.store` talks to `https://api.snapcraft.io` directly; the other groups go through the snapd socket (`/run/snapd.socket` by default).

## Usage

Get the list of installed snaps:

```python
# uses asyncio, must be run in an event loop
>>> import asyncio
>>> from snap_python.client import SnapClient
>>> sc = SnapClient()
>>> installed_snaps = asyncio.run(sc.snaps.list_installed_snaps())
>>> [snap.name for snap in installed_snaps.result]
[..., 'vlc', 'snapcraft', 'firefox', 'store-tui', 'gtk-common-themes', 'thunderbird', ...]
```

Get details for installed snap `vlc`

```python

# uses asyncio, must be run in an event loop
>>> import asyncio
>>> from snap_python.client import SnapClient
>>> sc = SnapClient()
>>> vlc_snap = asyncio.run(sc.snaps.get_snap_info("vlc"))
>>> vlc_snap.result.version
'3.0.20-1-g2617de71b6'
```

## License

This project is licensed under the MIT License. See the LICENSE file for more details.
