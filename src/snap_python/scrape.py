import pathlib

from snap_python.client import SnapClient
from snap_python.schemas.store.info import ChannelMapItem
from snap_python.schemas.store.refresh import VALID_SNAP_REFRESH_FIELDS


def get_highest_revision(channel_map: list[ChannelMapItem]) -> ChannelMapItem:
    print(channel_map)
    return max(channel_map, key=lambda x: x.revision)


async def get_all_snap_content(
    snap_client: SnapClient,
    snap_name: str,
    output_dir: pathlib.Path | str,
    start_revision: int = 1,
):
    if not isinstance(output_dir, pathlib.Path):
        output_dir = pathlib.Path(output_dir)

    if not output_dir.exists():
        output_dir.mkdir(parents=True)

    current_snap_info = await snap_client.store.get_snap_info(
        snap_name, fields=["name", "channel-map", "revision"]
    )
    current_snap_channel = get_highest_revision(current_snap_info.channel_map)

    print(
        f"Processing snap {snap_name} from revision {start_revision} to {current_snap_channel.revision}"
    )

    for revision in range(1, current_snap_channel.revision + 1):
        print(f"Processing revision {revision}")
        revision_dir = output_dir / str(revision)
        revision_dir.mkdir(exist_ok=True)
        # get snap revision info
        snap_revision_info = await snap_client.store.get_snap_revision_info(
            snap_name, revision, arch="amd64", fields=VALID_SNAP_REFRESH_FIELDS
        )

        snap_revision_data = snap_revision_info.results[0]

        with open(revision_dir / "data.json", "w") as f:
            f.write(snap_revision_data.model_dump_json(indent=2))

        # download snap revision
        snap_revision_download = snap_revision_data.snap.download.url

        # download the file
        snap_revision_download_path = (
            revision_dir / snap_revision_download.split("/")[-1]
        )

        store_client = snap_client.store.store_client
        async with store_client.stream(
            "GET", snap_revision_download, follow_redirects=True
        ) as response:
            with open(snap_revision_download_path, "wb") as f:
                async for chunk in response.aiter_bytes():
                    f.write(chunk)
