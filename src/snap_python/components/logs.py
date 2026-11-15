import logging
from typing import AsyncGenerator

from snap_python.schemas.logs import LogEntry
from snap_python.utils import AbstractSnapsClient

logger = logging.getLogger("snap_python.components.logs")

#: RFC 7464 record separator that prefixes every JSON-seq record.
RECORD_SEPARATOR = "\x1e"


def _parse_record(line: bytes) -> LogEntry | None:
    """Parse one JSON-seq line, returning None for anything unusable.

    Records look like ``<RS>{"timestamp": ...}\\n``. Truncated, empty or
    non-JSON records are skipped, exactly like snapd's own client. That also
    covers the raw ``\\x1E{"error": ...}`` record snapd writes when the journal
    read fails mid-stream: it has no real RS byte, so it is never JSON-seq.
    """
    text = line.decode("utf-8", errors="replace")
    index = text.find(RECORD_SEPARATOR)
    if index < 0:
        return None
    payload = text[index + 1 :].strip()
    if not payload:
        return None
    try:
        return LogEntry.model_validate_json(payload)
    except ValueError:
        logger.debug("Skipping malformed log record: %r", text)
        return None


class LogsEndpoints:
    """Endpoint for ``/v2/logs``, a JSON-seq journal stream.

    ``GET /v2/logs`` does not answer with the usual JSON envelope: it streams
    RFC 7464 records, each a record separator byte (``0x1E``), one JSON object
    and a newline. Errors raised before the stream starts are ordinary snapd
    error envelopes.

    Records are split on LF only. Neither :meth:`str.splitlines` nor httpx's
    ``aiter_lines`` may be used here: both treat the RS byte itself as a line
    boundary, which would shred every record.

    :param client: Client used to talk to snapd.
    """

    def __init__(self, client: AbstractSnapsClient) -> None:
        self._client = client
        self.common_endpoint = "logs"

    @staticmethod
    def _params(
        names: list[str] | None, n: int | None, follow: bool = False
    ) -> dict[str, str]:
        """Build the query parameters of ``GET /v2/logs``."""
        params: dict[str, str] = {}
        if names:
            params["names"] = ",".join(names)
        if n is not None:
            params["n"] = str(n)
        if follow:
            params["follow"] = "true"
        return params

    async def get_logs(
        self,
        names: list[str] | None = None,
        n: int | None = None,
    ) -> list[LogEntry]:
        """
        Retrieve a bounded batch of log entries.

        :param names: Services to read logs from, as ``"<snap>"`` or
            ``"<snap>.<app>"`` entries. Only services have logs. None (default)
            reads every service snapd can find.
        :type names: list[str], optional
        :param n: Number of lines snapd returns initially. ``-1`` means every
            line; None (default) omits the parameter, so snapd uses its own
            default of 10.
        :type n: int, optional

        :returns: The parsed log entries, in stream order.
        :rtype: list[LogEntry]

        :raises SnapdAPIError: If snapd answers with an error envelope, for
            example 404 when a name is not a service snap.
        :raises httpx.HTTPStatusError: If the request results in an HTTP error.
        """
        response = await self._client.request(
            "GET", self.common_endpoint, params=self._params(names, n)
        )
        entries = (_parse_record(line) for line in response.content.split(b"\n"))
        return [entry for entry in entries if entry is not None]

    async def stream_logs(
        self,
        names: list[str] | None = None,
        n: int | None = None,
    ) -> AsyncGenerator[LogEntry, None]:
        """
        Follow the log stream, yielding entries as snapd writes them.

        ``follow=true`` never terminates on its own, so this is an async
        generator: break out of the ``async for`` to close the stream. Unlike
        :meth:`get_logs` it needs the underlying ``httpx`` client, because
        :meth:`snap_python.client.SnapClient.request` buffers the whole body.
        Malformed records are skipped rather than raised on.

        :param names: Services to read logs from, as ``"<snap>"`` or
            ``"<snap>.app"`` entries. None (default) reads every service.
        :type names: list[str], optional
        :param n: Number of lines snapd replays before following. ``-1`` means
            every line; None (default) keeps snapd's default of 10.
        :type n: int, optional

        :yields: One parsed entry per record, in stream order.
        :rtype: LogEntry

        :raises SnapdAPIError: If snapd answers with an error envelope instead
            of a stream, for example 404 for an unknown service.
        :raises httpx.HTTPStatusError: If the request results in an HTTP error
            that is not a snapd envelope.
        :raises NotImplementedError: If the client does not expose the raw
            ``httpx`` client and its URL builder.
        """
        snapd_client = getattr(self._client, "snapd_client", None)
        build_url = getattr(self._client, "endpoint_url", None)
        if snapd_client is None or build_url is None:
            raise NotImplementedError(
                "log streaming needs a client exposing 'snapd_client' and "
                f"'endpoint_url()'; {type(self._client).__name__} is not usable"
            )

        params = self._params(names, n, follow=True)
        async with snapd_client.stream(
            "GET", build_url(self.common_endpoint), params=params
        ) as response:
            if response.is_error:
                await response.aread()
                # Imported lazily: snap_python.client imports this module.
                from snap_python.client import _snapd_error_from_response

                snapd_error = _snapd_error_from_response(response)
                if snapd_error is not None:
                    raise snapd_error
                response.raise_for_status()

            buffer = b""
            async for chunk in response.aiter_bytes():
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    entry = _parse_record(line)
                    if entry is not None:
                        yield entry
            if buffer:
                entry = _parse_record(buffer)
                if entry is not None:
                    yield entry
