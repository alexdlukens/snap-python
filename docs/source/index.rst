.. snap-python documentation master file, created by
   sphinx-quickstart on Sat Jan 18 14:29:45 2025.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

snap-python |version| documentation
===================================

Welcome to the documentation site for snap-python.

snap-python is an async Python client for the `snapd daemon <https://snapcraft.io/docs/get-started>`_ running on a local machine and for the `Snap Store <https://api.snapcraft.io>`_. It wraps the `snapd REST API <https://snapcraft.io/docs/snapd-api>`_ and the store's search API in an async HTTP client built on `httpx <https://www.python-httpx.org/>`_.

Quickstart
----------

.. code-block:: bash

   pip install snap-python

List the snaps installed on the local machine:

.. code-block:: python

   import asyncio

   from snap_python.client import SnapClient


   async def main() -> None:
       async with SnapClient() as client:
           response = await client.snaps.list_installed_snaps()
           for snap in response.result:
               # e.g. "firefox 128.0 stable"
               print(snap.name, snap.version, snap.tracking_channel)


   asyncio.run(main())

Reading state needs no root privileges; installing, removing, configuring and
connecting interfaces are forwarded to snapd, which asks for authorization
where it requires it.

What's in the client
--------------------

Every endpoint group is an attribute of :class:`snap_python.client.SnapClient`:

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - Attribute
     - Scope
   * - ``client.snaps``
     - Installed snaps: list, inspect, install, refresh, remove, hold, revert,
       switch channel, and start/stop/restart apps.
   * - ``client.config``
     - Read and write a snap's configuration (``snap set``/``snap get``).
   * - ``client.store``
     - Search the Snap Store, list categories, and inspect store-side snap
       details.
   * - ``client.changes``
     - List and inspect changes, abort pending changes, and watch one until it
       finishes.
   * - ``client.interfaces``
     - List interfaces and plug/slot connections, and connect or disconnect
       them.
   * - ``client.logs``
     - Read a bounded batch of service logs, or stream them as they are
       written.

.. note::

   ``client.snaps``, ``client.config``, ``client.changes``,
   ``client.interfaces`` and ``client.logs`` talk to snapd over its UNIX socket
   (``/run/snapd.socket`` by default). ``client.store`` instead talks to
   ``https://api.snapcraft.io`` directly, so store queries work without a
   running snapd.

More examples
-------------

Each snippet below runs inside the ``main()`` coroutine from the quickstart,
with ``SnapClient`` already imported.

Hold refreshes for a snap indefinitely:

.. code-block:: python

   async with SnapClient() as client:
       await client.snaps.hold_snap("firefox", time="forever")

Search the store:

.. code-block:: python

   async with SnapClient() as client:
       results = await client.store.find(query="video player")
       for snap in results.results:
           print(snap.name)

Follow service logs until you break out of the loop:

.. code-block:: python

   async with SnapClient() as client:
       # Logs exist only for services; pass names=["<snap>.<service>"] to
       # narrow the stream to a single one (that snap must expose a service).
       async for entry in client.logs.stream_logs(n=5):
           print(entry.timestamp, entry.message)
           if "error" in entry.message:
               break

.. toctree::
   :maxdepth: 4
   :caption: Contents:

   changelog
   modules/snap_python
