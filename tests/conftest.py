import logging

import pytest_asyncio

from snap_python.client import SnapClient
from tests.lib.setup_lxd_container import Container, setup_lxd_container, stop_container

logger = logging.getLogger("snap_python.tests.conftest")


@pytest_asyncio.fixture(scope="function", loop_scope="function")
async def function_scope_container() -> Container:
    container = setup_lxd_container("snap-python-test", clean=True)
    yield container
    stop_container("snap-python-test", container.client, remove=False)


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def module_scope_container() -> Container:
    container = setup_lxd_container("snap-python-test", clean=True)
    yield container
    stop_container("snap-python-test", container.client, remove=False)


@pytest_asyncio.fixture(scope="function", loop_scope="module")
async def module_scope_client(module_scope_container) -> SnapClient:
    container: Container = module_scope_container
    logger.info("Container ID: %s", container.name)
    yield SnapClient(version="v2", tcp_location="http://127.0.0.1:8181")


@pytest_asyncio.fixture(scope="function", loop_scope="function")
async def function_scope_client(function_scope_container) -> SnapClient:
    container: Container = function_scope_container
    logger.info("Container ID: %s", container.name)
    yield SnapClient(version="v2", tcp_location="http://127.0.0.1:8181")
