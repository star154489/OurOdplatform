"""Threaded wrapper that reads frames from an inner source on a background
daemon thread, buffering them for consumption on the main thread.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from enum import Enum, auto
from typing import Optional

from ..core.base import FrameSource, SeekTarget
from ..core.types import Frame

logger = logging.getLogger(__name__)

__all__ = ["ThreadedSource", "BufferStrategy"]

_EOS = object()
"""Internal sentinel pushed onto the buffer when the source is exhausted."""


class BufferStrategy(Enum):
    """Buffering strategy for :class:`ThreadedSource`.

    ``LATEST``
        Keep only the most recent frame (``maxsize=1``).  If the consumer
        is slower than the producer, older frames are silently discarded.
    ``BOUNDED``
        Keep up to ``maxsize`` frames.  When the buffer is full the oldest
        frame is discarded to make room for the new one.
    """

    LATEST = auto()
    BOUNDED = auto()


class ThreadedSource(FrameSource):
    """Wraps any :class:`FrameSource` and reads it on a background daemon
    thread.

    Frames are pushed into a thread-safe buffer from which the calling
    thread consumes.  This decouples I/O latency (e.g. camera read or
    network video) from processing.

    **Not seekable** — :meth:`seek` raises :class:`NotImplementedError`.

    Parameters
    ----------
    inner : FrameSource
        The underlying frame source to wrap.
    strategy : BufferStrategy or str
        ``BufferStrategy.LATEST`` (``"latest"``) or
        ``BufferStrategy.BOUNDED`` (``"bounded"``).
    maxsize : int
        Maximum buffer capacity (only meaningful for ``BOUNDED``).
        Ignored for ``LATEST`` (fixed at 1).
    warmup_frames : int
        Number of frames to pre-fill the buffer before the first
        :meth:`read` returns (helps absorb initial jitter).
    read_timeout : float
        Maximum seconds to wait for a frame from the buffer.
        If the timeout expires, ``None`` is returned and a warning is
        logged.  ``None`` means wait forever.
    """

    def __init__(
        self,
        inner: FrameSource,
        strategy: BufferStrategy | str = BufferStrategy.LATEST,
        maxsize: int = 30,
        warmup_frames: int = 0,
        read_timeout: float | None = None,
    ) -> None:
        self._inner = inner

        if isinstance(strategy, str):
            strategy = BufferStrategy[strategy.upper()]
        self._strategy = strategy

        self._maxsize = 1 if strategy == BufferStrategy.LATEST else max(1, int(maxsize))
        self._warmup_frames = max(0, int(warmup_frames))
        self._read_timeout = read_timeout

        # Thread-safe buffer
        self._buffer: deque = deque(maxlen=self._maxsize)
        self._lock = threading.Lock()
        self._not_empty = threading.Condition(self._lock)
        self._eos = False  # End-of-stream flag

        self._thread: threading.Thread | None = None
        self._running = False
        self._opened = False

    # -- life-cycle -------------------------------------------------------

    def open(self) -> None:
        if self._opened:
            return
        self._inner.open()
        self._buffer.clear()
        self._eos = False
        self._running = True

        self._thread = threading.Thread(
            target=self._reader_loop,
            name="ThreadedSource-reader",
            daemon=True,
        )
        self._thread.start()

        # Warm up: wait until at least warmup_frames are buffered.
        if self._warmup_frames > 0:
            with self._lock:
                while len(self._buffer) < self._warmup_frames and not self._eos:
                    self._not_empty.wait(timeout=1.0)

        self._opened = True

    def close(self) -> None:
        self._running = False
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None
        self._inner.close()
        with self._lock:
            self._buffer.clear()
            self._eos = True
            self._not_empty.notify_all()
        self._opened = False

    def read(self) -> Optional[Frame]:
        if not self._opened:
            raise RuntimeError("Source is not open. Call open() first.")

        with self._lock:
            if self._eos and not self._buffer:
                return None

            if not self._buffer:
                self._not_empty.wait(timeout=self._read_timeout)

            if not self._buffer:
                if self._eos:
                    return None
                logger.warning("ThreadedSource.read() timed out after %.2fs", self._read_timeout)
                return None

            frame = self._buffer.popleft()
            if frame is _EOS:
                self._eos = True
                return None
            return frame

    # -- unsupported operations -------------------------------------------

    def seek(self, target: SeekTarget) -> int:
        raise NotImplementedError("ThreadedSource does not support seeking.")

    def set_stride(self, n: int) -> None:
        # Pass through to inner (stride affects the underlying read loop).
        self._inner.set_stride(n)

    # -- background thread ------------------------------------------------

    def _reader_loop(self) -> None:
        """Daemon loop: reads frames from ``_inner`` and pushes them into
        the buffer."""
        try:
            while self._running:
                frame = self._inner.read()
                if frame is None:
                    # Source exhausted — push sentinel and stop.
                    with self._lock:
                        self._buffer.append(_EOS)
                        self._eos = True
                        self._not_empty.notify_all()
                    break

                with self._lock:
                    # For LATEST strategy, clear any stale frame first.
                    if self._strategy == BufferStrategy.LATEST:
                        self._buffer.clear()
                    self._buffer.append(frame)
                    self._not_empty.notify_all()
        except Exception:
            logger.exception("ThreadedSource reader loop crashed")
            with self._lock:
                self._buffer.append(_EOS)
                self._eos = True
                self._not_empty.notify_all()

    # -- meta -------------------------------------------------------------

    @property
    def source_type(self):
        return self._inner.source_type
