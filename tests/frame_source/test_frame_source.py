"""frame_source 模块全面测试。"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "apps" / "platform" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


# ---------- 数据类型 ----------

class TestFrameTypes:
    def test_source_type_values(self):
        from frame_source.core.types import SourceType
        assert SourceType.CAMERA.value == "camera"
        assert SourceType.VIDEO.value == "video"
        assert SourceType.IMAGE.value == "image"
        assert SourceType.IMAGE_FOLDER.value == "image_folder"

    def test_image_extensions(self):
        from frame_source.core.types import IMAGE_EXTENSIONS
        assert ".jpg" in IMAGE_EXTENSIONS
        assert ".png" in IMAGE_EXTENSIONS
        assert ".mp4" not in IMAGE_EXTENSIONS

    def test_video_extensions(self):
        from frame_source.core.types import VIDEO_EXTENSIONS
        assert ".mp4" in VIDEO_EXTENSIONS
        assert ".avi" in VIDEO_EXTENSIONS
        assert ".jpg" not in VIDEO_EXTENSIONS

    def test_frame_info(self):
        from frame_source.core.types import FrameInfo, SourceType
        info = FrameInfo(width=640, height=480, source_type=SourceType.IMAGE, filename="a.jpg")
        assert info.width == 640
        assert info.height == 480

    def test_frame(self):
        import numpy as np
        from frame_source.core.types import Frame, FrameInfo, SourceType
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        info = FrameInfo(width=640, height=480, source_type=SourceType.IMAGE)
        frame = Frame(image=img, info=info)
        assert frame.info.width == 640
        assert frame.info.height == 480


# ---------- CameraConfig ----------

class TestCameraConfig:
    def test_default_config(self):
        from frame_source.core.config import CameraConfig
        cfg = CameraConfig()
        assert cfg.camera_id == 0
        assert cfg.width >= 640
        assert cfg.fps == 30
        assert cfg.backend == "auto"

    def test_custom_config(self):
        from frame_source.core.config import CameraConfig
        cfg = CameraConfig(camera_id=1, width=1920, height=1080, fps=60, backend="msmf")
        assert cfg.camera_id == 1
        assert cfg.width == 1920
        assert cfg.height == 1080
        assert cfg.fps == 60
        assert cfg.backend == "msmf"

    def test_invalid_field_raises(self):
        from pydantic import ValidationError
        from frame_source.core.config import CameraConfig
        import pytest
        with pytest.raises(ValidationError):
            CameraConfig(width=-1)
        with pytest.raises(ValidationError):
            CameraConfig(backend="invalid")


# ---------- 工厂自动识别 ----------

class TestFactory:
    def test_camera_by_digit(self):
        from frame_source.factory import create_frame_source
        src = create_frame_source("0")
        from frame_source.sources.camera import CameraSource
        assert isinstance(src, CameraSource)

    def test_image_by_extension(self):
        from frame_source.factory import create_frame_source
        src = create_frame_source("test.jpg")
        from frame_source.sources.image import ImageSource
        assert isinstance(src, ImageSource)

    def test_image_png(self):
        from frame_source.factory import create_frame_source
        src = create_frame_source("photo.png")
        from frame_source.sources.image import ImageSource
        assert isinstance(src, ImageSource)

    def test_video_by_extension(self):
        from frame_source.factory import create_frame_source
        src = create_frame_source("video.mp4")
        from frame_source.sources.video import VideoSource
        assert isinstance(src, VideoSource)

    def test_video_rtsp(self):
        from frame_source.factory import create_frame_source
        src = create_frame_source("rtsp://192.168.1.1/stream")
        from frame_source.sources.video import VideoSource
        assert isinstance(src, VideoSource)

    def test_folder_by_directory(self):
        with tempfile.TemporaryDirectory() as d:
            from frame_source.factory import create_frame_source
            src = create_frame_source(d)
            from frame_source.sources.image import ImageFolderSource
            assert isinstance(src, ImageFolderSource)

    def test_threaded_shortcut(self):
        from frame_source.factory import create_threaded_source
        src = create_threaded_source("test.jpg")
        from frame_source.wrappers.threaded import ThreadedSource
        assert isinstance(src, ThreadedSource)


# ---------- ImageSource ----------

class TestImageSource:
    def test_open_nonexistent_raises(self):
        from frame_source.sources.image import ImageSource
        import pytest
        with pytest.raises(FileNotFoundError):
            ImageSource("nonexistent.jpg").open()

    def test_read_image(self):
        import numpy as np
        import cv2
        from frame_source.sources.image import ImageSource
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            tmp = f.name
        cv2.imwrite(tmp, np.zeros((100, 200, 3), dtype=np.uint8))
        try:
            with ImageSource(tmp) as src:
                frame = src.read()
                assert frame is not None
                assert frame.info.width == 200
                assert frame.info.height == 100
                assert frame.info.source_type.value == "image"
                assert src.read() is None  # 单图耗尽
        finally:
            Path(tmp).unlink(missing_ok=True)

    def test_reopen_resets(self):
        """验证重新 open 后能再次读到帧"""
        import numpy as np
        import cv2
        from frame_source.sources.image import ImageSource
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            tmp = f.name
        cv2.imwrite(tmp, np.zeros((50, 80, 3), dtype=np.uint8))
        try:
            src = ImageSource(tmp)
            src.open()
            f1 = src.read()
            assert f1 is not None
            src.close()
            src.open()
            f2 = src.read()
            assert f2 is not None, "重新 open 后应能再次读到帧"
        finally:
            Path(tmp).unlink(missing_ok=True)


# ---------- ImageFolderSource ----------

class TestImageFolderSource:
    def test_empty_folder_returns_none(self):
        from frame_source.sources.image import ImageFolderSource
        with tempfile.TemporaryDirectory() as d:
            src = ImageFolderSource(d)
            src.open()
            assert src.read() is None

    def test_read_folder_images(self):
        import numpy as np
        import cv2
        from frame_source.sources.image import ImageFolderSource
        with tempfile.TemporaryDirectory() as d:
            for i in range(3):
                cv2.imwrite(str(Path(d) / f"img_{i}.jpg"), np.zeros((10, 10, 3), dtype=np.uint8))
            with ImageFolderSource(d) as src:
                frames = list(src)
                assert len(frames) == 3

    def test_stride_skip(self):
        import numpy as np
        import cv2
        from frame_source.sources.image import ImageFolderSource
        with tempfile.TemporaryDirectory() as d:
            for i in range(10):
                cv2.imwrite(str(Path(d) / f"img_{i}.jpg"), np.zeros((10, 10, 3), dtype=np.uint8))
            with ImageFolderSource(d) as src:
                src.set_stride(3)
                frames = list(src)
                assert len(frames) == 4
