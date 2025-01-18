# snap-python

snap-python provides an API client to interact with snapd

[Click here to read the documentation](https://alexdlukens.github.io/snap-python/)

## Installation

To install snap-python, you can use pip:

```
pip install snap-python
```

## Usage

Here is a simple example of how to use snap-python:

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
