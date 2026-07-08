"""Async wrapper that exposes a synchronous :class:`FrameSource` as an
async generator using :func:`asyncio.to_thread` or
:func:`loop.run_in_executor`.
"""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncGenerator, AsyncIterator, Optional

from ..core.base import FrameSource, SeekTarget
from ..core.types import Frame

logger = logging.getLogger(__name__)

__all__ = ["AsyncSource"]


class AsyncSource(FrameSource):
    """Wraps any synchronous :class:`FrameSource` into an async interface.

    The heavy lifting (``open``, ``read``, ``close``) is offloaded to a
    thread pool via :func:`asyncio.to_thread` (Python 3.9+) or
    :func:`loop.run_in_executor`.

    Typical usage::

        source = AsyncSource(inner)
        await source.open()
        async for frame in source:
            ...

    .. note::

        ``seek()`` and ``set_stride()`` are **not** async-safe for most
        underlying sources and should be called before entering the async
        read loop.

    Parameters
    ----------
    inner : FrameSource
        The synchronous frame source to wrap.
    """

    def __init__(self, inner: FrameSource) -> None:
        self._inner = inner
        self._opened: bool = False
        self._loop: asyncio.AbstractEventLoop | None = None

    # -- async life-cycle helpers -----------------------------------------

    async def open(self) -> None:  # type: ignore[override]
        if self._opened:
            return
        self._loop = asyncio.get_running_loop()
        await asyncio.to_thread(self._inner.open)
        self._opened = True

    async def close(self) -> None:  # type: ignore[override]
        if not self._opened:
            return
        await asyncio.to_thread(self._inner.close)
        self._opened = False
        self._loop = None

    async def read(self) -> Optional[Frame]:  # type: ignore[override]
        if not self._opened:
            raise RuntimeError("Source is not open. Call open() first.")
        return await asyncio.to_thread(self._inner.read)

    def seek(self, target: SeekTarget) -> int:
        # Because seeking may affect internal state, we expose it
        # synchronously — call before the async loop.
        return self._inner.seek(target)

    def set_stride(self, n: int) -> None:
        # Stride should be set before the async loop.
        self._inner.set_stride(n)

    # -- async generator --------------------------------------------------

    async def async_generator(self) -> AsyncIterator[Frame]:
        """Return an async generator that yields frames until exhaustion.

        Example::

            async for frame in source.async_generator():
                process(frame)
        """
        while True:
            frame = await self.read()
            if frame is None:
                break
            yield frame

    # Make the class directly usable in ``async for``.
    def __aiter__(self) -> AsyncIterator[Frame]:
        return self.async_generator()

    # -- context manager --------------------------------------------------

    async def __aenter__(self) -> AsyncSource:
        await self.open()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        await self.close()

    # -- meta -------------------------------------------------------------

    @property
    def source_type(self):
        return self._inner.source_type

    @property
    def inner(self) -> FrameSource:
        return self._inner
