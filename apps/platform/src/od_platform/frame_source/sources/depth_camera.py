"""Frame source backed by a depth camera (e.g. RealSense, Kinect, Orbbec)."""

from __future__ import annotations

import logging
import time
from typing import Optional

import cv2
import numpy as np

from ..core.base import FrameSource, SeekTarget
from ..core.config import CameraConfig
from ..core.types import (
    Frame,
    FrameInfo,
    SourceType,
)
from ..registry import register_source

logger = logging.getLogger(__name__)

__all__ = ["DepthCameraSource"]


@register_source("depth_camera", description="Depth camera (e.g. RealSense / Kinect)")
def _create_depth_camera(source: str, config=None, **_kw):
    # source is e.g. "depth://0" — parse camera_id from it
    camera_id = 0
    if "://" in source:
        try:
            camera_id = int(source.split("://")[-1])
        except ValueError:
            camera_id = 0
    cfg = config or CameraConfig(camera_id=camera_id, camera_type="depth")
    return DepthCameraSource(cfg)


class DepthCameraSource(FrameSource):
    """A :class:`FrameSource` that reads depth frames from a depth sensor.

    Depth frames are returned as single-channel ``uint16`` arrays where
    each pixel value represents distance in the configured unit
    (millimetres by default).

    This implementation uses OpenCV's ``cv2.VideoCapture`` with the depth
    camera's device index. For advanced depth sensors (RealSense, Kinect),
    the depth stream is typically exposed as a separate camera device.

    Parameters
    ----------
    config : CameraConfig
        Camera configuration with ``camera_type="depth"``.
    """

    def __init__(self, config: CameraConfig | None = None) -> None:
        self._config = config or CameraConfig(camera_type="depth")
        self._cap: cv2.VideoCapture | None = None
        self._stride: int = 1
        self._opened: bool = False
        self._frame_index: int = -1

    # -- public API -------------------------------------------------------

    def open(self) -> None:
        if self._opened:
            return

        cfg = self._config
        backend_int = cfg.backend_int
        logger.info(
            "Opening depth camera %d (backend=%s, %dx%d @ %d fps)",
            cfg.camera_id, cfg.backend, cfg.width, cfg.height, cfg.fps,
        )

        self._cap = cv2.VideoCapture(cfg.camera_id, backend_int)
        if not self._cap.isOpened():
            raise RuntimeError(
                f"Failed to open depth camera {cfg.camera_id} "
                f"with backend {cfg.backend}"
            )

        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.height)
        if cfg.codec:
            self._cap.set(cv2.CAP_PROP_FOURCC, cfg.fourcc)
        self._cap.set(cv2.CAP_PROP_FPS, cfg.fps)

        # Negotiation frame
        ret, _ = self._cap.read()
        if not ret:
            logger.warning(
                "Depth camera %d: first frame read failed (may still work)",
                cfg.camera_id,
            )

        self._frame_index = -1
        self._opened = True

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        self._frame_index = -1
        self._opened = False

    def read(self) -> Optional[Frame]:
        if not self._opened or self._cap is None:
            raise RuntimeError("Source is not open. Call open() first.")

        ret, frame = self._cap.read()
        if not ret or frame is None:
            logger.warning(
                "Depth camera %d: read returned False", self._config.camera_id
            )
            return None

        # Depth streams from OpenCV cameras typically come as 3-channel BGR
        # where depth info is encoded. Convert to single-channel uint16
        # depth map. If the frame is already single-channel, keep it as-is.
        if frame.ndim == 3 and frame.shape[2] == 3:
            # Convert BGR to grayscale 16-bit depth approximation
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            depth = gray.astype(np.uint16)
            # Scale 0-255 → 0-65535 range for mm-level precision
            depth = depth * 257
        elif frame.ndim == 2:
            depth = frame.astype(np.uint16) if frame.dtype != np.uint16 else frame
        else:
            depth = frame

        self._frame_index += 1
        info = FrameInfo(
            width=depth.shape[1],
            height=depth.shape[0],
            source_type=SourceType.DEPTH_CAMERA,
            frame_index=self._frame_index,
            total_frames=None,
            timestamp=time.monotonic(),
            fps=self._cap.get(cv2.CAP_PROP_FPS) or None,
            filename=f"depth:{self._config.camera_id}",
        )
        return Frame(image=depth, info=info)

    def seek(self, target: SeekTarget) -> int:
        raise NotImplementedError("DepthCameraSource does not support seeking.")

    def set_stride(self, n: int) -> None:
        if n != 1:
            logger.warning(
                "DepthCameraSource does not support stride; "
                "locking to 1 (requested %d)", n
            )
        self._stride = 1

    # -- meta -------------------------------------------------------------

    @property
    def source_type(self) -> SourceType:
        return SourceType.DEPTH_CAMERA

    @property
    def config(self) -> CameraConfig:
        return self._config
