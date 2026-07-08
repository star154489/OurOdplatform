"""Abstract base class defining the :class:`FrameSource` protocol."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Iterator, Optional, Union

from .types import Frame

logger = logging.getLogger(__name__)

__all__ = ["FrameSource"]

SeekTarget = Union[int, float]
"""Type accepted by ``seek()`` — an integer frame index or a float time
(in seconds, for video-type sources)."""


class FrameSource(ABC):
    """Abstract protocol for unified frame input.

    Every source in the ``frame_source`` module implements this interface,
    making swapping between camera, video, image, and image-folder sources
    transparent.

    **Context-manager support** (:source:`with` statement)::

        with source:
            for frame in source:
                ...

    **Iterator support** (calls :meth:`read` repeatedly)::

        for frame in source:
            ...

    All implementations **must** define the abstract methods below.
    """

    # -- life-cycle -------------------------------------------------------

    @abstractmethod
    def open(self) -> None:
        """Open / initialise the underlying resource.

        *Camera*   — open the device handle.
        *Video*    — open the video file or stream.
        *Image*    — a no-op (the file path is stored); state is reset.
        *Folder*   — scan and sort the directory; state is reset.

        Calling ``open()`` on an already-opened source should be a no-op or
        idempotent. Subclasses may raise :class:`RuntimeError` on failure.
        """
        ...

    @abstractmethod
    def close(self) -> None:
        """Release the underlying resource.

        After ``close()``, the source should be reusable via another
        ``open()`` call.
        """
        ...

    @abstractmethod
    def read(self) -> Optional[Frame]:
        """Read the next frame.

        Returns
        -------
        Frame or None
            A :class:`Frame` containing the image and metadata, or
            ``None`` when the stream is exhausted.
        """
        ...

    # -- seeking ----------------------------------------------------------

    @abstractmethod
    def seek(self, target: SeekTarget) -> int:
        """Seek to a *frame index* or a *time in seconds*.

        Parameters
        ----------
        target : int or float
            - ``int``  — zero-based frame index to seek to.
            - ``float`` — time in seconds (for video / camera streams with
              known FPS).  For image-based sources only integer indices are
              accepted.

        Returns
        -------
        int
            The actual frame index reached after seeking (may differ from
            the requested value if the source clamps or rounds).

        Raises
        ------
        NotImplementedError
            If the source type does not support seeking (e.g. camera).
        ValueError
            If the target is out of range or of the wrong type.
        """
        ...

    # -- stride -----------------------------------------------------------

    @abstractmethod
    def set_stride(self, n: int) -> None:
        """Configure frame stride.

        When *stride* ``N > 1``, the source will skip ``N-1`` frames
        between every returned frame (i.e. returns every *N*-th frame).

        *Video sources* should implement this by calling
        :meth:`cv2.VideoCapture.grab` (zero-IO skip) for maximum
        performance.

        *Camera sources* typically **do not** support stride and should
        issue a warning, locking stride to ``1``.

        Parameters
        ----------
        n : int
            Stride value (``1`` = return every frame).
        """
        ...

    # -- convenience protocol methods -------------------------------------

    def __enter__(self) -> FrameSource:
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        self.close()

    def __iter__(self) -> Iterator[Frame]:
        return self

    def __next__(self) -> Frame:
        frame = self.read()
        if frame is None:
            raise StopIteration
        return frame
