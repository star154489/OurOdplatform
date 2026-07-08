"""``frame_source`` — a self-contained, portable module for unified frame
input from 4 sources: camera, video, single image, and image folder.

Minimal dependencies: ``numpy``, ``opencv-python``, ``pydantic>=2.0``,
and Python stdlib.
"""

from __future__ import annotations

from .core import (
    CameraConfig,
    Frame,
    FrameInfo,
    FrameSource,
    IMAGE_EXTENSIONS,
    SourceType,
    VIDEO_EXTENSIONS,
)
from .factory import (
    create_async_source,
    create_frame_source,
    create_threaded_source,
)
from .sources import (
    CameraSource,
    ImageFolderSource,
    ImageSource,
    VideoSource,
)
from .wrappers import AsyncSource, ThreadedSource

__all__ = [
    # core types
    "SourceType",
    "FrameInfo",
    "Frame",
    "IMAGE_EXTENSIONS",
    "VIDEO_EXTENSIONS",
    "CameraConfig",
    "FrameSource",
    # sources
    "CameraSource",
    "VideoSource",
    "ImageSource",
    "ImageFolderSource",
    # wrappers
    "ThreadedSource",
    "AsyncSource",
    # factory
    "create_frame_source",
    "create_threaded_source",
    "create_async_source",
]
