"""Frame source backed by a physical or virtual camera device."""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

import cv2

from ..core.base import FrameSource, SeekTarget
from ..core.config import CameraConfig
from ..core.types import (
    Frame,
    FrameInfo,
    SourceType,
)

logger = logging.getLogger(__name__)

__all__ = ["CameraSource"]

# ---------------------------------------------------------------------------
# Environment variable for MSMF on Windows
# ---------------------------------------------------------------------------
_MSMF_DISABLED_VAR = "OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS"
"""Setting this env var to ``"0"`` can fix MSMF initialisation issues on
some Windows configurations. The :class:`CameraSource` does this
automatically when the backend is ``"msmf"`` or ``"auto"`` on Windows."""


class CameraSource(FrameSource):
    """A :class:`FrameSource` that reads frames from a camera device.

    Camera parameters are supplied via a :class:`CameraConfig`.  The
    configuration is applied in the order recommended by OpenCV:
    ``width → height → FOURCC → FPS``.  After configuration one frame is
    read to trigger negotiation, and the actual vs requested parameters
    are compared.

    **Camera sources do not support stride** — calling :meth:`set_stride`
    with ``N > 1`` logs a warning and resets stride to ``1``.

    Parameters
    ----------
    config : CameraConfig
        Camera configuration (see :class:`CameraConfig`).
    """

    def __init__(self, config: CameraConfig | None = None) -> None:
        self._config = config or CameraConfig()
        self._cap: cv2.VideoCapture | None = None
        self._stride: int = 1
        self._opened: bool = False
        self._frame_index: int = -1

    # -- public API -------------------------------------------------------

    def open(self) -> None:
        if self._opened:
            return

        cfg = self._config

        # On Windows with auto/MSMF backend, disable HW transforms to
        # avoid common init failures.
        if os.name == "nt" and cfg.backend in ("auto", "msmf"):
            if _MSMF_DISABLED_VAR not in os.environ:
                os.environ[_MSMF_DISABLED_VAR] = "0"
                logger.debug("Set %s=0 for MSMF compatibility", _MSMF_DISABLED_VAR)

        backend_int = cfg.backend_int
        logger.info(
            "Opening camera %d (backend=%s, codec=%s, %dx%d @ %d fps)",
            cfg.camera_id,
            cfg.backend,
            cfg.codec,
            cfg.width,
            cfg.height,
            cfg.fps,
        )

        self._cap = cv2.VideoCapture(cfg.camera_id, backend_int)
        if not self._cap.isOpened():
            raise RuntimeError(
                f"Failed to open camera {cfg.camera_id} with backend {cfg.backend}"
            )

        # Apply parameters in recommended order: width, height, FOURCC, FPS.
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.height)
        if cfg.codec:
            self._cap.set(cv2.CAP_PROP_FOURCC, cfg.fourcc)
        self._cap.set(cv2.CAP_PROP_FPS, cfg.fps)

        # Read one frame to trigger internal negotiation.
        ret, _ = self._cap.read()
        if not ret:
            logger.warning("Camera %d: first frame read failed (may still work)", cfg.camera_id)

        # Verify actual vs requested.
        actual_w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        actual_fps = self._cap.get(cv2.CAP_PROP_FPS)
        logger.info(
            "Camera %d negotiated: %dx%d @ %.2f fps (requested %dx%d @ %d fps)",
            cfg.camera_id,
            actual_w,
            actual_h,
            actual_fps,
            cfg.width,
            cfg.height,
            cfg.fps,
        )
        if actual_w != cfg.width or actual_h != cfg.height:
            logger.warning(
                "Camera %d: resolution mismatch — requested %dx%d, got %dx%d",
                cfg.camera_id,
                cfg.width,
                cfg.height,
                actual_w,
                actual_h,
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

        ret, bgr = self._cap.read()
        if not ret or bgr is None:
            logger.warning("Camera %d: read returned False", self._config.camera_id)
            return None

        self._frame_index += 1
        info = FrameInfo(
            width=bgr.shape[1],
            height=bgr.shape[0],
            source_type=SourceType.CAMERA,
            frame_index=self._frame_index,
            total_frames=None,  # live stream
            timestamp=time.monotonic(),
            fps=self._cap.get(cv2.CAP_PROP_FPS) or None,
            filename=f"camera:{self._config.camera_id}",
        )
        return Frame(image=bgr, info=info)

    def seek(self, target: SeekTarget) -> int:
        raise NotImplementedError("CameraSource does not support seeking.")

    def set_stride(self, n: int) -> None:
        if n != 1:
            logger.warning(
                "CameraSource does not support stride; locking to 1 (requested %d)", n
            )
        self._stride = 1

    # -- meta -------------------------------------------------------------

    @property
    def source_type(self) -> SourceType:
        return SourceType.CAMERA

    @property
    def config(self) -> CameraConfig:
        return self._config
