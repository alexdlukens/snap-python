import logging
import subprocess

import pylxd
import pylxd.exceptions
import pylxd.managers
import pylxd.models
import pylxd.models.container
from pylxd.models import Container, Image, Project

logger = logging.getLogger("pysnap.tests.lib.setup_lxd_container")
logger.setLevel(logging.INFO)
logger.handlers.clear()
logger.addHandler(logging.StreamHandler())


def list_images_on_machine(client: pylxd.Client = None):
    if client is None:
        client = pylxd.Client()
    imagemanager: Image = client.images
    images = imagemanager.all()
    image: Image
    logger.info("Retrieved %s images", len(images))
    for image in images:
        logger.info(
            "Image: %s - %s - %s", image.fingerprint, image.aliases, image.architecture
        )


def add_image_to_system(
    name: str,
    version: str = "sid",
    variant: str = "default",
    client: pylxd.Client = None,
) -> str:
    if client is None:
        client = pylxd.Client()

    imagemanager: Image = client.images
    alias = f"{name}/{version}/{variant}"
    # check if image already exists
    images = imagemanager.all()
    image: Image
    for image in images:
        if alias in [a["name"] for a in image.aliases]:
            logger.info("Image %s already exists, returning", alias)
            return alias

    # use subprocess to add image
    logger.info("Adding image %s to system", alias)
    subprocess.run(
        [
            "lxc",
            "image",
            "copy",
            f"images:{alias}",
            "local:",
            "--alias",
            alias,
            "--auto-update",
            "--project",
            client.project or "default",
        ],
        check=True,
    )

    # get the image
    try:
        list_images_on_machine(client)
        image = imagemanager.get_by_alias(alias)
    except pylxd.exceptions.NotFound:
        logger.error("Image %s not found", alias)
        raise

    logger.info("Added image %s to system as %s", image.fingerprint, alias)

    return alias


def get_project_client(project: str) -> pylxd.Client:
    client = pylxd.Client()
    # check if project exists
    project_manager: Project = client.projects
    try:
        project_manager.get(project)
    except pylxd.exceptions.NotFound:
        logger.info("Creating project %s", project)
        project_manager.create(project)
    client = pylxd.Client(project=project)

    return client


def stop_container(container_name: str, client: pylxd.Client, remove: bool = True):
    container_manager: Container = client.containers
    try:
        container: Container = container_manager.get(container_name)
    except pylxd.exceptions.LXDAPIException:
        container = None

    if container is None:
        logger.info("Container does not exist, returning")
        return

    if container.status != "Stopped":
        logger.info("Container is in state %s, stopping", container.status)
        container.stop(wait=True)

    if remove:
        logger.info("Removing container")
        container.delete(wait=True)

    logger.info("Container removed")


def ensure_snapd_clean_install(container: Container):
    container.execute(
        ["apt-get", "update", "-y"],
        stdout_handler=logger.debug,
        stderr_handler=logger.error,
    )
    container.execute(
        ["apt-get", "install", "-y", "snapd"],
        stdout_handler=logger.debug,
        stderr_handler=logger.error,
    )

    # remove all existing snaps
    # list all snaps
    snap_list = container.execute(
        ["snap", "list", "|", "tail", "-n", "+2", "|", "awk", "'{print $1}'"]
    )
    snap_list = snap_list.stdout.split("\n")
    for snap in snap_list:
        if snap:
            logger.info("Removing snap %s", snap)
            container_response = container.execute(["snap", "remove", "--purge", snap])
            logger.info("Response: %s", container_response.stdout.decode("utf-8"))


def setup_lxd_container(
    container_name: str,
    container_os: str = "debian",
    version: str = "sid",
    variant: str = "default",
    project: str = "pysnap",
    clean: bool = False,
) -> Container:
    client = get_project_client(project)
    # ensure image exists
    image_alias = add_image_to_system(
        name=container_os, version=version, variant=variant, client=client
    )
    if clean:
        logger.info("Attempting to clean up container %s", container_name)
        stop_container(container_name, client, remove=True)

    container_manager: Container = client.containers
    try:
        container: Container = container_manager.get(container_name)
    except pylxd.exceptions.LXDAPIException:
        container = None

    if container is None:
        logger.info("Container does not exist, creating from image: %s", image_alias)
        # create container
        container = container_manager.create(
            {
                "name": container_name,
                "source": {"type": "image", "alias": image_alias},
                "devices": {
                    "root": {
                        "type": "disk",
                        "path": "/",
                        "pool": "default",
                    }
                },
            },
            wait=True,
        )
        # Setup default network
        container.devices.update(
            {"eth0": {"name": "eth0", "network": "lxdbr0", "type": "nic"}}
        )
        container.save(wait=True)

    if container.status != "Running":
        logger.info("Container is in state %s, starting", container.status)
        container.start(wait=True)

    logger.info("Container started, cleaning up snapd")
    ensure_snapd_clean_install(container)

    logger.info("Container %s is ready", container.name)
    return container