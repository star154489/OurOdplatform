"""Factory functions for creating :class:`FrameSource` instances from a
variety of input specifiers.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from .core.base import FrameSource
from .core.config import CameraConfig
from .core.types import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS
from .registry import get_source
from .wrappers.aio import AsyncSource
from .wrappers.threaded import ThreadedSource

logger = logging.getLogger(__name__)

__all__ = [
    "create_frame_source",
    "create_threaded_source",
    "create_async_source",
]

# Regex: detect if *source* looks like a URL (scheme://...)
_URL_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9+\-.]*://")

# URI scheme → source type mapping (e.g. "depth://" → "depth_camera")
_URI_SCHEME_MAP: dict[str, str] = {}


def register_uri_scheme(scheme: str, source_type: str) -> None:
    """Register a URI scheme → source_type mapping for auto-detection.

    Example: ``register_uri_scheme("depth", "depth_camera")`` makes
    ``"depth://0"`` resolve to the ``"depth_camera"`` source type.
    """
    _URI_SCHEME_MAP[scheme] = source_type


def _is_url(s: str) -> bool:
    return bool(_URL_PATTERN.match(s))


def _infer_source_type(source: str) -> str:
    """Infer the source type from the *source* string.

    Returns one of the keys registered in the source registry
    (e.g. ``"camera"``, ``"image"``, ``"video"``, ``"image_folder"``,
    ``"depth_camera"``, ``"ir_camera"``).
    """
    # 0) URI scheme check: e.g. "depth://0", "ir://1"
    match = _URL_PATTERN.match(source)
    if match:
        scheme = match.group().rstrip("://")
        if scheme in _URI_SCHEME_MAP:
            return _URI_SCHEME_MAP[scheme]
        # Standard URL (rtsp, http, etc.) → video
        return "video"

    # 1) All digits → camera index
    if source.isdigit():
        return "camera"

    # 2) URL without special scheme → video
    if _is_url(source):
        return "video"

    path = Path(source)

    # 3) Existing directory → image folder
    if path.is_dir():
        return "image_folder"

    # 4) Known image extension → single image
    if path.suffix.lower() in IMAGE_EXTENSIONS:
        return "image"

    # 5) Known video extension → video file
    if path.suffix.lower() in VIDEO_EXTENSIONS:
        return "video"

    # 6) Fallback: treat as video (may fail at open time).
    logger.warning("Could not infer source type for %r — assuming video", source)
    return "video"


def create_frame_source(
    source: str,
    config: Optional[CameraConfig] = None,
    threaded: bool = False,
    **kwargs,
) -> FrameSource:
    """Create a :class:`FrameSource` by auto-detecting the type of
    *source*.

    Parameters
    ----------
    source : str
        One of:

        * Camera index (digits only, e.g. ``"0"``, ``"1"``)
        * Path to an image file (e.g. ``"frame.jpg"``)
        * Path to a video file (e.g. ``"video.mp4"``)
        * URL to a network stream (e.g. ``"rtsp://..."``)
        * Path to a directory of images
        * Special URI scheme (e.g. ``"depth://0"``, ``"ir://1"``)

    config : CameraConfig or None
        Only used when *source* is a camera index.  If ``None`` a default
        :class:`CameraConfig` is created.

    threaded : bool
        If ``True``, wrap the source in a :class:`ThreadedSource`.

    **kwargs
        Additional keyword arguments forwarded to the wrapper
        constructors (e.g. ``strategy``, ``maxsize``,
        ``warmup_frames``, ``read_timeout``).

    Returns
    -------
    FrameSource
        A ready-to-use frame source (call ``.open()`` to initialise).
    """
    source_type = _infer_source_type(source)

    # Look up the registered factory for this source type.
    entry = get_source(source_type)
    inner: FrameSource = entry.factory(source, config=config)

    if threaded:
        # Pop threaded-specific kwargs: strategy, maxsize, warmup_frames,
        # read_timeout — anything else is silently ignored.
        strategy = kwargs.pop("strategy", None)
        maxsize = kwargs.pop("maxsize", 30)
        warmup_frames = kwargs.pop("warmup_frames", 0)
        read_timeout = kwargs.pop("read_timeout", None)
        inner = ThreadedSource(
            inner,
            strategy=strategy or "latest",
            maxsize=maxsize,
            warmup_frames=warmup_frames,
            read_timeout=read_timeout,
        )

    return inner


def create_threaded_source(
    source: str,
    config: Optional[CameraConfig] = None,
    **kwargs,
) -> ThreadedSource:
    """Shortcut that creates a :class:`ThreadedSource` wrapping the
    auto-detected inner source.

    Equivalent to ``create_frame_source(source, config, threaded=True, **kwargs)``.
    """
    result = create_frame_source(source, config, threaded=True, **kwargs)
    # The result is always a ThreadedSource when threaded=True.
    assert isinstance(result, ThreadedSource)
    return result


def create_async_source(
    source: str,
    config: Optional[CameraConfig] = None,
    threaded: bool = False,
    **kwargs,
) -> AsyncSource:
    """Shortcut that wraps the auto-detected inner source in an
    :class:`AsyncSource`.

    Parameters
    ----------
    source : str
        Source specifier (camera index, file path, URL, etc.).
    config : CameraConfig or None
        Camera configuration (only used for camera sources).
    threaded : bool
        If ``True``, first wrap in a :class:`ThreadedSource` before the
        async wrapper, giving better concurrency.
    **kwargs
        Forwarded to the inner factory.

    Returns
    -------
    AsyncSource
    """
    inner = create_frame_source(source, config, threaded=threaded, **kwargs)
    return AsyncSource(inner)


# ── URI scheme registrations ─────────────────────────────────────────
# Called at import time so "depth://0" and "ir://1" auto-resolve.
register_uri_scheme("depth", "depth_camera")
register_uri_scheme("ir", "ir_camera")
