"""Frame source backed by an infrared (IR) camera."""

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

__all__ = ["IRCameraSource"]


@register_source("ir_camera", description="Infrared (IR) thermal camera")
def _create_ir_camera(source: str, config=None, **_kw):
    camera_id = 0
    if "://" in source:
        try:
            camera_id = int(source.split("://")[-1])
        except ValueError:
            camera_id = 0
    cfg = config or CameraConfig(camera_id=camera_id, camera_type="ir")
    return IRCameraSource(cfg)


class IRCameraSource(FrameSource):
    """A :class:`FrameSource` that reads frames from an infrared camera.

    IR frames are returned as single-channel grayscale ``uint8`` or
    ``uint16`` arrays (depending on the sensor). The pixel intensity
    represents thermal radiation — brighter = hotter.

    Parameters
    ----------
    config : CameraConfig
        Camera configuration with ``camera_type="ir"``.
    """

    def __init__(self, config: CameraConfig | None = None) -> None:
        self._config = config or CameraConfig(camera_type="ir")
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
            "Opening IR camera %d (backend=%s, %dx%d @ %d fps)",
            cfg.camera_id, cfg.backend, cfg.width, cfg.height, cfg.fps,
        )

        self._cap = cv2.VideoCapture(cfg.camera_id, backend_int)
        if not self._cap.isOpened():
            raise RuntimeError(
                f"Failed to open IR camera {cfg.camera_id} "
                f"with backend {cfg.backend}"
            )

        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.height)
        if cfg.codec:
            self._cap.set(cv2.CAP_PROP_FOURCC, cfg.fourcc)
        self._cap.set(cv2.CAP_PROP_FPS, cfg.fps)

        ret, _ = self._cap.read()
        if not ret:
            logger.warning(
                "IR camera %d: first frame read failed (may still work)",
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
                "IR camera %d: read returned False", self._config.camera_id
            )
            return None

        # Convert to single-channel grayscale for IR data.
        if frame.ndim == 3 and frame.shape[2] == 3:
            ir_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        elif frame.ndim == 2:
            ir_frame = frame
        else:
            ir_frame = frame

        self._frame_index += 1
        info = FrameInfo(
            width=ir_frame.shape[1],
            height=ir_frame.shape[0],
            source_type=SourceType.IR_CAMERA,
            frame_index=self._frame_index,
            total_frames=None,
            timestamp=time.monotonic(),
            fps=self._cap.get(cv2.CAP_PROP_FPS) or None,
            filename=f"ir:{self._config.camera_id}",
        )
        return Frame(image=ir_frame, info=info)

    def seek(self, target: SeekTarget) -> int:
        raise NotImplementedError("IRCameraSource does not support seeking.")

    def set_stride(self, n: int) -> None:
        if n != 1:
            logger.warning(
                "IRCameraSource does not support stride; "
                "locking to 1 (requested %d)", n
            )
        self._stride = 1

    # -- meta -------------------------------------------------------------

    @property
    def source_type(self) -> SourceType:
        return SourceType.IR_CAMERA

    @property
    def config(self) -> CameraConfig:
        return self._config
