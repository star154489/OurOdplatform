"""Frame sources backed by a single image or a directory of images."""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from ..core.base import FrameSource, SeekTarget
from ..core.types import (
    IMAGE_EXTENSIONS,
    Frame,
    FrameInfo,
    SourceType,
)
from ..registry import register_source

logger = logging.getLogger(__name__)

__all__ = [
    "ImageSource",
    "ImageFolderSource",
]


@register_source("image", description="Single image file")
def _create_image(source: str, config=None, **_kw):
    return ImageSource(source)


@register_source("image_folder", description="Directory of image files")
def _create_image_folder(source: str, config=None, **_kw):
    return ImageFolderSource(source)


class ImageSource(FrameSource):
    """A :class:`FrameSource` that reads a single image file.

    The frame is returned once; subsequent ``read()`` calls return ``None``
    until :meth:`open` is called again (which resets the internal read
    counter).

    Parameters
    ----------
    path : str or Path
        Path to an image file (any format supported by OpenCV's
        :func:`cv2.imread`).
    """

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self._path = Path(path)
        self._image: np.ndarray | None = None
        self._read_count: int = 0
        self._stride: int = 1
        self._opened: bool = False

    # -- public API -------------------------------------------------------

    def open(self) -> None:
        if self._opened:
            return
        if not self._path.is_file():
            raise FileNotFoundError(f"Image not found: {self._path}")
        # Load on first read, not here, to keep open() light and idempotent.
        self._read_count = 0
        self._opened = True

    def close(self) -> None:
        self._image = None
        self._read_count = 0
        self._opened = False

    def read(self) -> Optional[Frame]:
        if not self._opened:
            raise RuntimeError("Source is not open. Call open() first.")
        if self._read_count > 0:
            return None

        # Load (and cache) the image on first read.
        if self._image is None:
            img = cv2.imread(str(self._path))
            if img is None:
                raise ValueError(f"Failed to read image: {self._path}")
            self._image = img

        self._read_count += 1
        info = FrameInfo(
            width=self._image.shape[1],
            height=self._image.shape[0],
            source_type=SourceType.IMAGE,
            frame_index=0,
            total_frames=1,
            timestamp=time.monotonic(),
            filename=str(self._path),
        )
        # Return a copy so the caller can mutate it safely.
        return Frame(image=self._image.copy(), info=info)

    def seek(self, target: SeekTarget) -> int:
        if isinstance(target, float):
            raise TypeError("ImageSource does not support time-based seeking.")
        if target < 0:
            raise ValueError(f"Frame index must be >= 0, got {target}")
        if target == 0:
            # Reset so next read() returns the image again.
            self._read_count = 0
            return 0
        # Only frame 0 is available — mark as exhausted.
        self._read_count = 1
        return 0

    def set_stride(self, n: int) -> None:
        self._stride = max(1, int(n))

    # -- meta -------------------------------------------------------------

    @property
    def source_type(self) -> SourceType:
        return SourceType.IMAGE


class ImageFolderSource(FrameSource):
    """A :class:`FrameSource` that reads all images from a directory.

    Images are sorted alphabetically. Corrupt or unreadable images are
    skipped with a warning. Stride is implemented as zero-IO index skipping
    (the file is never even opened).

    Parameters
    ----------
    path : str or Path
        Path to a directory containing image files.
    """

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self._root = Path(path)
        self._image_paths: list[Path] = []
        self._current_index: int = 0
        self._stride: int = 1
        self._opened: bool = False
        self._total_frames: int = 0

    # -- public API -------------------------------------------------------

    def open(self) -> None:
        if self._opened:
            return
        if not self._root.is_dir():
            raise NotADirectoryError(f"Not a directory: {self._root}")

        # Gather and sort image paths.
        all_files: list[Path] = sorted(self._root.iterdir(), key=lambda p: p.name)
        self._image_paths = [p for p in all_files if p.suffix.lower() in IMAGE_EXTENSIONS]

        if not self._image_paths:
            logger.warning("No image files found in %s", self._root)

        self._total_frames = len(self._image_paths)
        self._current_index = 0
        self._opened = True
        logger.info("ImageFolderSource: %d images in %s", self._total_frames, self._root)

    def close(self) -> None:
        self._image_paths.clear()
        self._current_index = 0
        self._total_frames = 0
        self._opened = False

    def read(self) -> Optional[Frame]:
        if not self._opened:
            raise RuntimeError("Source is not open. Call open() first.")

        # Apply stride: skip indices.
        while self._current_index < self._total_frames:
            idx = self._current_index
            self._current_index += self._stride

            path = self._image_paths[idx]
            img = cv2.imread(str(path))
            if img is None:
                logger.warning("Skipping corrupt/unreadable image: %s", path)
                continue

            info = FrameInfo(
                width=img.shape[1],
                height=img.shape[0],
                source_type=SourceType.IMAGE_FOLDER,
                frame_index=idx,
                total_frames=self._total_frames,
                timestamp=time.monotonic(),
                filename=str(path),
            )
            return Frame(image=img, info=info)

        return None

    def seek(self, target: SeekTarget) -> int:
        if isinstance(target, float):
            raise TypeError("ImageFolderSource does not support time-based seeking.")
        if not self._opened:
            raise RuntimeError("Source is not open.")
        if target < 0:
            raise ValueError(f"Frame index must be >= 0, got {target}")

        # Clamp to valid range, respecting stride so we always land on a
        # stride-aligned index.
        new_index = min(target, self._total_frames - 1) if self._total_frames > 0 else 0
        self._current_index = new_index
        return self._current_index

    def set_stride(self, n: int) -> None:
        self._stride = max(1, int(n))

    # -- meta -------------------------------------------------------------

    @property
    def source_type(self) -> SourceType:
        return SourceType.IMAGE_FOLDER
