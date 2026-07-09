"""Core type definitions for the frame_source module.

Defines the Frame data container, metadata types, and file-extension
frozensets that are the single source of truth for the entire module.
"""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

# ---------------------------------------------------------------------------
# File extension constants — single source of truth
# ---------------------------------------------------------------------------

IMAGE_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".jpg",
        ".jpeg",
        ".png",
        ".bmp",
        ".tiff",
        ".tif",
        ".webp",
        ".ppm",
        ".pgm",
        ".pbm",
        ".sr",
        ".ras",
        ".exr",
        ".hdr",
        ".pfm",
    }
)

VIDEO_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".mp4",
        ".avi",
        ".mov",
        ".mkv",
        ".wmv",
        ".flv",
        ".webm",
        ".m4v",
        ".mpg",
        ".mpeg",
        ".mts",
        ".m2ts",
        ".ts",
        ".3gp",
        ".ogv",
        ".vob",
    }
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SourceType(str, enum.Enum):
    """Identifies the type of frame source."""

    CAMERA = "camera"
    DEPTH_CAMERA = "depth_camera"
    IR_CAMERA = "ir_camera"
    VIDEO = "video"
    IMAGE = "image"
    IMAGE_FOLDER = "image_folder"


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------


@dataclass
class FrameInfo:
    """Metadata associated with a single frame.

    Attributes
    ----------
    width : int
        Pixel width of the frame.
    height : int
        Pixel height of the frame.
    source_type : SourceType
        The type of source that produced this frame.
    frame_index : int
        Zero-based index of this frame within its source stream.
    total_frames : Optional[int]
        Total number of frames in the source, if known (``None`` for cameras
        and live streams).
    timestamp : float
        Monotonic timestamp (seconds) when the frame was read.
    fps : Optional[float]
        Nominal frames-per-second of the source, if known.
    filename : Optional[str]
        Source filename or identifier (e.g. device name, URL, path).
    """

    width: int = 0
    height: int = 0
    source_type: SourceType = SourceType.IMAGE
    frame_index: int = 0
    total_frames: Optional[int] = None
    timestamp: float = field(default_factory=time.monotonic)
    fps: Optional[float] = None
    filename: Optional[str] = None


@dataclass
class Frame:
    """A single frame produced by a :class:`FrameSource`.

    Attributes
    ----------
    image : np.ndarray
        BGR-ordered image array of shape ``(H, W, 3)`` and dtype ``uint8``.
    info : FrameInfo
        Metadata describing this frame.
    """

    image: np.ndarray
    info: FrameInfo = field(default_factory=FrameInfo)

    def __post_init__(self) -> None:
        if self.image is not None and self.info.width == 0:
            self.info.width = self.image.shape[1]
            self.info.height = self.image.shape[0]
