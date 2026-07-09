"""Pydantic configuration model for camera sources."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

__all__ = ["CameraConfig"]

CameraBackend = Literal["auto", "msmf", "dshow", "v4l2"]
CameraCodec = Literal["MJPG", "YUYV", "H264", "MP4V"]
CameraType = Literal["rgb", "depth", "ir"]
DepthUnit = Literal["mm", "m"]


class CameraConfig(BaseModel):
    """Configuration for a camera (webcam / USB / built-in) source.

    All fields have sensible defaults so that ``CameraConfig()`` produces a
    working configuration for the default camera (index ``0``) at VGA
    resolution.

    Parameters
    ----------
    camera_id : int
        OS camera index (``0`` = first detected camera).
    width : int
        Desired frame width in pixels.
    height : int
        Desired frame height in pixels.
    fps : int
        Desired frames-per-second.
    backend : CameraBackend
        Preferred backend. ``"auto"`` lets OpenCV pick. Use ``"msmf"`` on
        Windows for Media Foundation, ``"dshow"`` for DirectShow, or
        ``"v4l2"`` on Linux.
    codec : CameraCodec
        FourCC codec hint (e.g. ``"MJPG"`` for motion-JPEG, ``"YUYV"`` for
        raw YUV, ``"H264"`` for H.264, ``"MP4V"`` for MPEG-4).
    camera_type : CameraType
        Sensor type: ``"rgb"`` (default), ``"depth"``, or ``"ir"``.
    depth_unit : DepthUnit
        Unit for depth camera frames: ``"mm"`` (default) or ``"m"``.
    """

    model_config = {"extra": "forbid", "validate_assignment": True}

    camera_id: int = Field(default=0, ge=0)
    width: int = Field(default=640, ge=1)
    height: int = Field(default=480, ge=1)
    fps: int = Field(default=30, ge=1)
    backend: CameraBackend = Field(default="auto")
    codec: CameraCodec = Field(default="MJPG")
    camera_type: CameraType = Field(default="rgb")
    depth_unit: DepthUnit = Field(default="mm")

    # -- public helpers ---------------------------------------------------

    @property
    def backend_int(self) -> int:
        """Return the OpenCV ``cv2.CAP_*`` constant for the selected backend.

        Returns ``0`` (``cv2.CAP_ANY``) for ``"auto"``.
        """
        import cv2

        mapping: dict[str, int] = {
            "auto": cv2.CAP_ANY,
            "msmf": cv2.CAP_MSMF,
            "dshow": cv2.CAP_DSHOW,
            "v4l2": cv2.CAP_V4L2,
        }
        return mapping.get(self.backend, cv2.CAP_ANY)

    @property
    def fourcc(self) -> float | int:
        """Return the FOURCC code as a float or int for ``cv2.CAP_PROP_FOURCC``."""
        import cv2

        return cv2.VideoWriter.fourcc(
            self.codec[0], self.codec[1], self.codec[2], self.codec[3]
        )

    # -- validators -------------------------------------------------------

    @field_validator("backend")
    @classmethod
    def _normalise_backend(cls, v: str) -> str:
        allowed = {"auto", "msmf", "dshow", "v4l2"}
        if v.lower() not in allowed:
            msg = f"backend must be one of {allowed}, got {v!r}"
            raise ValueError(msg)
        return v.lower()

    @field_validator("codec")
    @classmethod
    def _normalise_codec(cls, v: str) -> str:
        allowed = {"MJPG", "YUYV", "H264", "MP4V"}
        upper = v.upper()
        if upper not in allowed:
            msg = f"codec must be one of {allowed}, got {v!r}"
            raise ValueError(msg)
        return upper
