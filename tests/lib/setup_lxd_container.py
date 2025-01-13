import logging
import subprocess
from pathlib import Path

import pylxd
import pylxd.exceptions
import pylxd.managers
import pylxd.models
import pylxd.models.container
from pylxd.models import Container, Image, Project

TEST_DIR = Path(__file__).parent.parent
TEST_LIB_DIR = TEST_DIR / "lib"
SOCAT_SERVICE_FILE = TEST_LIB_DIR / "socat_snapd.service"

logger = logging.getLogger("snap_python.tests.lib.setup_lxd_container")
logger.setLevel(logging.INFO)


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
    version: str = "bookworm",
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
        ["sudo", "apt-get", "update", "-y"],
        stdout_handler=logger.debug,
        stderr_handler=logger.error,
    )
    container.execute(
        [
            "sudo",
            "apt-get",
            "install",
            "-y",
            "libsquashfuse0",
            "squashfuse",
            "fuse",
            "curl",
            "socat",
            "snapd",
        ],
        stdout_handler=logger.debug,
        stderr_handler=logger.error,
    )

    with open(SOCAT_SERVICE_FILE, "rb") as f:
        container.files.put("/etc/systemd/system/socat_snapd.service", f.read())

    # ensure snapd is up to date
    container.execute(
        ["sudo", "snap", "install", "snapd"],
        stdout_handler=logger.debug,
        stderr_handler=logger.error,
    )

    # ensure snapd is up to date
    container.execute(
        ["sudo", "snap", "refresh", "snapd"],
        stdout_handler=logger.debug,
        stderr_handler=logger.error,
    )

    logger.info("Starting socat service")
    # ensure socat service is enabled
    container.execute(
        [
            "sudo",
            "systemctl",
            "enable",
            "socat_snapd.service",
        ],
        stdout_handler=logger.debug,
        stderr_handler=logger.error,
    )
    container.execute(
        [
            "sudo",
            "systemctl",
            "start",
            "socat_snapd.service",
        ],
        stdout_handler=logger.debug,
        stderr_handler=logger.error,
    )


def setup_lxd_container(
    container_name: str,
    container_os: str = "debian",
    version: str = "bookworm",
    variant: str = "default",
    project: str = "snap-python",
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
        container.devices.update(
            {
                "snapd_socket": {
                    "bind": "host",
                    "listen": "tcp:127.0.0.1:8181",
                    "connect": "tcp:127.0.0.1:8181",
                    "type": "proxy",
                }
            }
        )

        container.save(wait=True)

    if container.status != "Running":
        logger.info("Container is in state %s, starting", container.status)
        container.start(wait=True)

    logger.info("Container started, cleaning up snapd")
    ensure_snapd_clean_install(container)

    logger.info("Container %s is ready", container.name)
    return container


# socat cmd: socat TCP-LISTEN:8181,fork UNIX-CONNECT:/run/snapd.socket
