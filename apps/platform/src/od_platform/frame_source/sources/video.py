"""Frame source backed by a video file or network stream."""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Optional

import cv2

from ..core.base import FrameSource, SeekTarget
from ..core.types import (
    Frame,
    FrameInfo,
    SourceType,
)
from ..registry import register_source

logger = logging.getLogger(__name__)

__all__ = ["VideoSource"]


@register_source("video", description="Video file or network stream (RTSP/HTTP)")
def _create_video(source: str, config=None, **_kw):
    return VideoSource(source)

_FPS_FALLBACK: float = 30.0
"""Fallback framerate used when OpenCV reports 0 or missing fps."""


class VideoSource(FrameSource):
    """A :class:`FrameSource` that reads frames from a video file or
    network stream (RTSP, HTTP, etc.).

    Stride is implemented via :meth:`cv2.VideoCapture.grab` which performs
    zero-IO (or minimal-IO) skips — typically 3-5× faster than decoding and
    discarding frames.

    Parameters
    ----------
    path : str or Path
        Path to a video file or a URL (RTSP, HTTP live stream, etc.).
    """

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self._path = str(path)  # keep as string — OpenCV accepts URLs
        self._cap: cv2.VideoCapture | None = None
        self._fps: float = _FPS_FALLBACK
        self._total_frames: int = 0
        self._frame_index: int = -1  # last successfully read index
        self._stride: int = 1
        self._opened: bool = False

    # -- public API -------------------------------------------------------

    def open(self) -> None:
        if self._opened:
            return

        self._cap = cv2.VideoCapture(self._path)
        if not self._cap.isOpened():
            raise RuntimeError(f"Failed to open video source: {self._path}")

        # Read metadata
        total = self._cap.get(cv2.CAP_PROP_FRAME_COUNT)
        self._total_frames = int(total) if total > 0 else 0

        fps = self._cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0:
            logger.warning(
                "Video '%s' reports FPS=%.2f — falling back to %.1f",
                self._path,
                fps,
                _FPS_FALLBACK,
            )
            fps = _FPS_FALLBACK
        self._fps = fps

        self._frame_index = -1
        self._opened = True
        logger.info(
            "VideoSource opened: %s (%d frames @ %.2f fps)",
            self._path,
            self._total_frames,
            self._fps,
        )

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        self._frame_index = -1
        self._opened = False

    def read(self) -> Optional[Frame]:
        if not self._opened or self._cap is None:
            raise RuntimeError("Source is not open. Call open() first.")

        # Skip N-1 frames via grab() for performance.
        for _ in range(self._stride - 1):
            if not self._cap.grab():
                return None

        ret, bgr = self._cap.read()
        if not ret or bgr is None:
            return None

        self._frame_index += 1
        info = FrameInfo(
            width=bgr.shape[1],
            height=bgr.shape[0],
            source_type=SourceType.VIDEO,
            frame_index=self._frame_index,
            total_frames=self._total_frames if self._total_frames > 0 else None,
            timestamp=time.monotonic(),
            fps=self._fps,
            filename=self._path,
        )
        return Frame(image=bgr, info=info)

    def seek(self, target: SeekTarget) -> int:
        if not self._opened or self._cap is None:
            raise RuntimeError("Source is not open.")

        if isinstance(target, float):
            # Time-based seek
            target_frame = int(round(target * self._fps))
        elif isinstance(target, int):
            target_frame = target
        else:
            raise TypeError(f"Unsupported seek target type: {type(target)}")

        target_frame = max(0, target_frame)
        if self._total_frames > 0:
            target_frame = min(target_frame, self._total_frames - 1)

        # cv2.CAP_PROP_POS_FRAMES is 0-based; set then read to finalise.
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
        self._frame_index = target_frame - 1  # next read() will increment
        return target_frame

    def set_stride(self, n: int) -> None:
        self._stride = max(1, int(n))

    # -- meta -------------------------------------------------------------

    @property
    def source_type(self) -> SourceType:
        return SourceType.VIDEO

    @property
    def fps(self) -> float:
        return self._fps
