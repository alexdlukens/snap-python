import pathlib

from snap_python.client import SnapClient
from snap_python.schemas.store.info import ChannelMapItem
from snap_python.schemas.store.refresh import VALID_SNAP_REFRESH_FIELDS


def get_highest_revision(channel_map: list[ChannelMapItem]) -> ChannelMapItem:
    """Find the ChannelMapItem with the highest revision number from a list of ChannelMapItems.

    Find the highest revision in a provided channel map

    Parameters:
        channel_map (list[ChannelMapItem]): A list of ChannelMapItem objects to search through.

    Returns:
        ChannelMapItem: The item with the highest revision number

    Example:

        >>> items = [ChannelMapItem(revision=1), ChannelMapItem(revision=5), ChannelMapItem(revision=3)]
        >>> highest = get_highest_revision(items)
        >>> highest.revision
        5

    """

    return max(channel_map, key=lambda x: x.revision)


async def download_snap_file(
    snap_client: SnapClient,
    snap_revision_download: str,
    snap_revision_download_path: pathlib.Path,
):
    """Asynchronously downloads a snap file from the Snap Store.

    This function streams the snap file from the specified URL and writes it to
    the specified path on disk.

    Parameters:
        snap_client (SnapClient): The client for interacting with the Snap Store.
        snap_revision_download (str): The URL to download the snap file from.
        snap_revision_download_path (pathlib.Path): The path where the downloaded snap file will be saved.

    Returns:
        None

    """

    store_client = snap_client.store.store_client
    async with store_client.stream(
        "GET", snap_revision_download, follow_redirects=True
    ) as response:
        with open(snap_revision_download_path, "wb") as f:
            async for chunk in response.aiter_bytes():
                f.write(chunk)


async def get_all_snap_content(
    snap_client: SnapClient,
    snap_name: str,
    output_dir: pathlib.Path | str,
    start_revision: int = 1,
    with_snap_files: bool = False,
):
    """
    Asynchronously fetches and downloads all content for a specified snap package across multiple revisions.

    This function retrieves metadata for each revision of a snap package and optionally downloads
    the snap files themselves. All content is organized into directories by revision number.

    Parameters:
        snap_client (SnapClient): Initialized Snap client instance for API interactions.
        snap_name (str): Name of the snap package to process.
        output_dir (pathlib.Path | str): Directory where snap content will be saved.
        start_revision (int, optional): First revision to process. Defaults to 1.
        with_snap_files (bool, optional): Whether to download the actual snap package files. Defaults to False.

    Returns:
        None

    Notes:
        - Creates a directory structure where each revision has its own subdirectory
        - Saves metadata as data.json in each revision directory
        - When with_snap_files=True, also downloads the snap package file for each revision

    """
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

        if with_snap_files:
            await download_snap_file(
                snap_client, snap_revision_download, snap_revision_download_path
            )
