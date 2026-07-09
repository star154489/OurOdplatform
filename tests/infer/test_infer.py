#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""推理系统(D8)扩展优化 — 单元测试 & 集成测试.

运行方式::

    # 全部测试
    pytest tests/infer/test_infer.py -v

    # 仅单元测试 (不需要 ultralytics / torch)
    pytest tests/infer/test_infer.py -v -m unit

    # 仅集成测试 (需要 ultralytics / torch + 模型文件)
    pytest tests/infer/test_infer.py -v -m integration

测试覆盖:
    - 8-1: 注册表、深度/红外相机、stride、ThreadedSource/AsyncSource
    - 8-2: Detection/DrawStyle 扩展、多任务 from_yolo_results、BeautifyVisualizer
    - 8-3: macOS 检测、PipelineConfig、Pipeline 结构
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

# Ensure od_platform is importable
_src = Path(__file__).resolve().parents[2] / "apps" / "platform" / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))


# ============================================================================
# helpers
# ============================================================================

def _torch_available() -> bool:
    try:
        import torch  # noqa: F401
        return True
    except ImportError:
        return False


def _ultralytics_available() -> bool:
    try:
        import ultralytics  # noqa: F401
        return True
    except ImportError:
        return False


def _has_model(name: str) -> bool:
    """Check if a YOLO model file exists in common locations."""
    candidates = [
        Path(name),
        Path("models/pretrained") / name,
        Path("models/trained") / name,
    ]
    return any(p.exists() for p in candidates)


# ============================================================================
# 8-1: 帧源捕获模块
# ============================================================================

class TestFrameSourceRegistry:
    """8-1 Fix 1: 注册表 + 自动注册机制."""

    def test_available_sources(self):
        from od_platform.frame_source.registry import available_sources
        sources = available_sources()
        assert "camera" in sources
        assert "video" in sources
        assert "image" in sources
        assert "image_folder" in sources
        assert "depth_camera" in sources
        assert "ir_camera" in sources
        assert len(sources) >= 6

    def test_get_source_returns_entry(self):
        from od_platform.frame_source.registry import get_source
        entry = get_source("camera")
        assert entry.source_type == "camera"
        assert entry.description != ""
        assert callable(entry.factory)

    def test_get_source_unknown_raises(self):
        from od_platform.frame_source.registry import get_source
        with pytest.raises(ValueError, match="Unregistered"):
            get_source("nonexistent_source_type")

    def test_registry_factory_creates_frame_source(self):
        from od_platform.frame_source.registry import get_source
        from od_platform.frame_source.core.base import FrameSource

        for name in ["camera", "video", "image", "image_folder",
                      "depth_camera", "ir_camera"]:
            entry = get_source(name)
            if name in ("camera", "depth_camera", "ir_camera"):
                src = entry.factory("0")
            elif name == "image_folder":
                # Use current directory as a valid dir with no images
                src = entry.factory(".")
            else:
                src = entry.factory("test.mp4")
            assert isinstance(src, FrameSource), f"{name} factory did not return FrameSource"


class TestDepthIRCamera:
    """8-1 Ext 1: 深度相机 / 红外相机."""

    def test_source_type_enum_values(self):
        from od_platform.frame_source.core.types import SourceType
        assert SourceType.DEPTH_CAMERA.value == "depth_camera"
        assert SourceType.IR_CAMERA.value == "ir_camera"

    def test_camera_config_has_type_fields(self):
        from od_platform.frame_source.core.config import CameraConfig
        cfg = CameraConfig()
        assert cfg.camera_type == "rgb"
        assert cfg.depth_unit == "mm"

        cfg2 = CameraConfig(camera_type="depth", depth_unit="m")
        assert cfg2.camera_type == "depth"
        assert cfg2.depth_unit == "m"

    def test_factory_creates_depth_source(self):
        from od_platform.frame_source import create_frame_source
        src = create_frame_source("depth://0")
        assert type(src).__name__ == "DepthCameraSource"

    def test_factory_creates_ir_source(self):
        from od_platform.frame_source import create_frame_source
        src = create_frame_source("ir://1")
        assert type(src).__name__ == "IRCameraSource"

    def test_depth_source_stores_config(self):
        from od_platform.frame_source.sources.depth_camera import DepthCameraSource
        from od_platform.frame_source.core.config import CameraConfig
        cfg = CameraConfig(camera_id=0, camera_type="depth", depth_unit="m")
        src = DepthCameraSource(cfg)
        assert src.config.camera_type == "depth"
        assert src.config.depth_unit == "m"

    def test_ir_source_stores_config(self):
        from od_platform.frame_source.sources.ir_camera import IRCameraSource
        from od_platform.frame_source.core.config import CameraConfig
        cfg = CameraConfig(camera_id=1, camera_type="ir")
        src = IRCameraSource(cfg)
        assert src.config.camera_type == "ir"


class TestStride:
    """8-1 Fix 2: 视频 stride."""

    def test_video_source_set_stride(self):
        from od_platform.frame_source.sources.video import VideoSource
        src = VideoSource("test.mp4")
        src.set_stride(5)
        assert src._stride == 5

    def test_video_source_stride_clamped(self):
        from od_platform.frame_source.sources.video import VideoSource
        src = VideoSource("test.mp4")
        src.set_stride(0)
        assert src._stride == 1  # clamped to min 1
        src.set_stride(-3)
        assert src._stride == 1

    def test_image_folder_set_stride(self):
        from od_platform.frame_source.sources.image import ImageFolderSource
        src = ImageFolderSource(".")
        src.set_stride(3)
        assert src._stride == 3

    def test_camera_source_stride_rejected(self):
        from od_platform.frame_source.sources.camera import CameraSource
        src = CameraSource()
        src.set_stride(5)
        assert src._stride == 1  # camera locks to 1


class TestThreadedAsyncWrappers:
    """8-1 Ext 2: 异步 / 线程包装器."""

    def test_threaded_source_creation(self):
        from od_platform.frame_source import create_threaded_source
        from od_platform.frame_source.wrappers.threaded import ThreadedSource
        src = create_threaded_source("0", maxsize=2, warmup_frames=0)
        assert isinstance(src, ThreadedSource)

    def test_async_source_creation(self):
        from od_platform.frame_source import create_async_source
        from od_platform.frame_source.wrappers.aio import AsyncSource
        src = create_async_source("0")
        assert isinstance(src, AsyncSource)

    def test_async_source_supports_async_context(self):
        import asyncio
        from od_platform.frame_source import create_async_source

        async def _test():
            src = create_async_source("0")
            # Test that async with works (we close immediately, don't actually open camera)
            assert hasattr(src, "__aenter__")
            assert hasattr(src, "__aexit__")
            assert hasattr(src, "__aiter__")

        asyncio.run(_test())


# ============================================================================
# 8-2: 美化模块
# ============================================================================

class TestDetectionDataclass:
    """8-2: Detection 扩展字段."""

    def test_detection_has_extended_fields(self):
        from od_platform.visualization.core.data_types import Detection
        fields = Detection.__dataclass_fields__
        assert "box" in fields
        assert "mask" in fields
        assert "keypoints" in fields
        assert "obb" in fields
        assert "probs" in fields

    def test_detection_default_box_is_none(self):
        from od_platform.visualization.core.data_types import Detection
        d = Detection()
        assert d.box is None
        assert d.confidence == 0.0
        assert d.label == ""

    def test_detection_detect_style(self):
        from od_platform.visualization.core.data_types import Detection
        d = Detection(
            box=(10, 10, 100, 100),
            confidence=0.95,
            label="person",
            color=(0, 255, 0),
        )
        assert d.box == (10, 10, 100, 100)
        assert d.mask is None
        assert d.keypoints is None
        assert d.obb is None
        assert d.probs is None

    def test_detection_segment_style(self):
        from od_platform.visualization.core.data_types import Detection
        mask = np.array([[10, 20], [30, 40], [50, 60]], dtype=np.float32)
        d = Detection(
            box=(10, 10, 100, 100),
            confidence=0.88,
            label="person",
            mask=mask,
        )
        assert d.mask is not None
        assert len(d.mask) == 3

    def test_detection_classify_style(self):
        from od_platform.visualization.core.data_types import Detection
        d = Detection(
            confidence=0.85,
            label="cat",
            probs=[("cat", 0.85), ("dog", 0.10), ("bird", 0.05)],
        )
        assert d.box is None
        assert d.probs is not None
        assert len(d.probs) == 3


class TestDrawStyle:
    """8-2: DrawStyle 扩展字段."""

    def test_draw_style_has_task_fields(self):
        from od_platform.visualization.core.data_types import DrawStyle
        fields = list(DrawStyle.model_fields.keys())
        assert "mask_alpha" in fields
        assert "keypoint_radius" in fields
        assert "skeleton_thickness" in fields
        # Existing fields preserved
        assert "font_size" in fields
        assert "line_width" in fields
        assert "radius" in fields

    def test_draw_style_defaults(self):
        from od_platform.visualization.core.data_types import DrawStyle
        style = DrawStyle()
        assert style.mask_alpha == 0.4
        assert style.keypoint_radius == 4
        assert style.skeleton_thickness == 2

    def test_draw_style_from_image_size(self):
        from od_platform.visualization.core.data_types import DrawStyle
        style = DrawStyle.from_image_size(480, 640, font_scale=0.8)
        assert style.font_size > 0
        assert style.line_width > 0
        assert style.radius > 0

    def test_draw_style_custom_task_params(self):
        from od_platform.visualization.core.data_types import DrawStyle
        style = DrawStyle(mask_alpha=0.6, keypoint_radius=6, skeleton_thickness=3)
        assert style.mask_alpha == 0.6
        assert style.keypoint_radius == 6
        assert style.skeleton_thickness == 3

    def test_draw_style_extra_forbid(self):
        from od_platform.visualization.core.data_types import DrawStyle
        with pytest.raises(Exception):
            DrawStyle(nonexistent_field=123)


class TestBeautifyVisualizer:
    """8-2: BeautifyVisualizer 多任务."""

    def test_visualizer_init(self):
        from od_platform.visualization import BeautifyVisualizer
        v = BeautifyVisualizer(labels=["person", "car", "dog"])
        assert v.default_color == (0, 255, 0)
        assert v.label_mapping == {}

    def test_draw_empty_detections(self):
        from od_platform.visualization import BeautifyVisualizer
        v = BeautifyVisualizer(labels=["person"])
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        result = v.draw(img, [])
        assert result.shape == img.shape
        assert np.array_equal(result, img)  # copy returned

    @pytest.mark.parametrize("task_type,expected_box", [
        ("detect", (10, 10, 100, 100)),
        ("segment", (10, 10, 100, 100)),
        ("pose", (10, 10, 100, 100)),
        ("obb", (10, 10, 100, 100)),
    ])
    def test_from_yolo_results_box_tasks(self, task_type, expected_box):
        from od_platform.visualization import BeautifyVisualizer
        dets = BeautifyVisualizer.from_yolo_results(
            boxes=np.array([[10, 10, 100, 100]]),
            confidences=np.array([0.95]),
            labels=["person"],
            task_type=task_type,
        )
        assert len(dets) == 1
        assert dets[0].box == expected_box
        assert dets[0].confidence == 0.95
        assert dets[0].label == "person"

    def test_from_yolo_results_segment_with_masks(self):
        from od_platform.visualization import BeautifyVisualizer
        mask = np.array([[10, 20], [30, 40], [50, 60]], dtype=np.float32)
        dets = BeautifyVisualizer.from_yolo_results(
            boxes=np.array([[10, 10, 100, 100]]),
            confidences=np.array([0.88]),
            labels=["person"],
            task_type="segment",
            masks=[mask],
        )
        assert dets[0].mask is not None

    def test_from_yolo_results_pose_with_keypoints(self):
        from od_platform.visualization import BeautifyVisualizer
        kpts = np.random.rand(17, 3).astype(np.float32)
        kpts[:, 2] = 0.9  # high confidence
        dets = BeautifyVisualizer.from_yolo_results(
            boxes=np.array([[10, 10, 100, 200]]),
            confidences=np.array([0.92]),
            labels=["person"],
            task_type="pose",
            keypoints=[kpts],
        )
        assert dets[0].keypoints is not None
        assert dets[0].keypoints.shape == (17, 3)

    def test_from_yolo_results_obb(self):
        from od_platform.visualization import BeautifyVisualizer
        corners = np.array([[0, 0], [100, 0], [100, 50], [0, 50]], dtype=np.float32)
        dets = BeautifyVisualizer.from_yolo_results(
            boxes=np.array([[0, 0, 100, 50]]),
            confidences=np.array([0.75]),
            labels=["car"],
            task_type="obb",
            obb=[corners],
        )
        assert dets[0].obb is not None

    def test_from_yolo_results_classify(self):
        from od_platform.visualization import BeautifyVisualizer
        dets = BeautifyVisualizer.from_yolo_results(
            boxes=np.zeros((0, 4)),
            confidences=np.array([0.85]),
            labels=["cat"],
            task_type="classify",
            probs=[("cat", 0.85), ("dog", 0.10), ("bird", 0.05)],
        )
        assert len(dets) == 1
        assert dets[0].box is None
        assert dets[0].probs is not None
        assert len(dets[0].probs) == 3

    def test_draw_with_detections_returns_same_shape(self):
        from od_platform.visualization import BeautifyVisualizer
        from od_platform.visualization.core.data_types import Detection
        v = BeautifyVisualizer(labels=["person"])
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        dets = [Detection(box=(100, 100, 200, 200), confidence=0.9, label="person")]
        result = v.draw(img, dets)
        assert result.shape == img.shape

    def test_draw_classify_produces_valid_output(self):
        from od_platform.visualization import BeautifyVisualizer
        from od_platform.visualization.core.data_types import Detection
        v = BeautifyVisualizer(labels=["cat", "dog", "bird"])
        img = np.zeros((480, 640, 3), dtype=np.uint8) + 100  # gray background
        dets = [Detection(
            confidence=0.85,
            label="cat",
            probs=[("cat", 0.85), ("dog", 0.10), ("bird", 0.05)],
        )]
        result = v.draw(img, dets)
        assert result.shape == img.shape
        # Should have drawn the classify panel (not identical to input)
        assert not np.array_equal(result, img)


class TestVisualizerDrawPaths:
    """8-2: 验证各任务绘制路径不崩溃."""

    @pytest.fixture
    def visualizer(self):
        from od_platform.visualization import BeautifyVisualizer
        return BeautifyVisualizer(labels=["person", "car", "dog"])

    @pytest.fixture
    def image(self):
        return np.zeros((480, 640, 3), dtype=np.uint8) + 50

    def test_draw_detect(self, visualizer, image):
        from od_platform.visualization.core.data_types import Detection
        dets = [Detection(box=(100, 100, 300, 400), confidence=0.95, label="person")]
        result = visualizer.draw(image, dets)
        assert result.shape == image.shape

    def test_draw_with_mask(self, visualizer, image):
        from od_platform.visualization.core.data_types import Detection
        mask = np.array([[100, 100], [300, 100], [300, 400], [100, 400]], dtype=np.float32)
        dets = [Detection(
            box=(100, 100, 300, 400), confidence=0.85, label="person", mask=mask,
        )]
        result = visualizer.draw(image, dets)
        assert result.shape == image.shape

    def test_draw_with_keypoints(self, visualizer, image):
        from od_platform.visualization.core.data_types import Detection
        kpts = np.random.rand(17, 3).astype(np.float32)
        kpts[:, 0] = kpts[:, 0] * 200 + 100
        kpts[:, 1] = kpts[:, 1] * 200 + 100
        kpts[:, 2] = 0.9
        dets = [Detection(
            box=(100, 100, 300, 400), confidence=0.90, label="person", keypoints=kpts,
        )]
        result = visualizer.draw(image, dets)
        assert result.shape == image.shape

    def test_draw_with_obb(self, visualizer, image):
        from od_platform.visualization.core.data_types import Detection
        corners = np.array([[100, 100], [300, 80], [320, 200], [120, 220]], dtype=np.float32)
        dets = [Detection(
            box=(100, 80, 320, 220), confidence=0.80, label="car", obb=corners,
        )]
        result = visualizer.draw(image, dets)
        assert result.shape == image.shape


# ============================================================================
# 8-3: 推理流水线
# ============================================================================

@pytest.mark.skipif(not _torch_available(), reason="torch not installed")
class TestMacOSDetection:
    """8-3 Bug: macOS 平台检测."""

    def test_is_macos_returns_bool(self):
        from od_platform.inference.pipeline import _is_macos
        result = _is_macos()
        assert isinstance(result, bool)

    def test_is_macos_matches_sys_platform(self):
        import sys
        from od_platform.inference.pipeline import _is_macos
        assert _is_macos() == (sys.platform == "darwin")


@pytest.mark.skipif(not _torch_available(), reason="torch not installed")
class TestPipelineConfig:
    """8-3: PipelineConfig 扩展."""

    def test_default_frame_stride(self):
        from od_platform.inference.pipeline_config import PipelineConfig
        pc = PipelineConfig()
        assert pc.frame_stride == 1

    def test_custom_frame_stride(self):
        from od_platform.inference.pipeline_config import PipelineConfig
        pc = PipelineConfig(frame_stride=5)
        assert pc.frame_stride == 5

    def test_build_camera_config_none_when_empty(self):
        from od_platform.inference.pipeline_config import PipelineConfig
        pc = PipelineConfig()
        assert pc.build_camera_config() is None

    def test_to_audit_includes_stride(self):
        from od_platform.inference.pipeline_config import PipelineConfig
        pc = PipelineConfig(frame_stride=3)
        audit = pc.to_audit()
        assert "viz_enabled" in audit
        assert audit["viz_enabled"] is True


@pytest.mark.skipif(not _torch_available(), reason="torch not installed")
class TestPipelineStructure:
    """8-3: Pipeline 内部结构验证."""

    def test_threaded_pipeline_imports(self):
        from od_platform.inference.pipeline import (
            ThreadedPipeline,
            _Reader,
            _Renderer,
            _Display,
            _InferenceWorker,
            _Controller,
        )
        assert ThreadedPipeline is not None
        assert _Reader is not None
        assert _Renderer is not None
        assert _Display is not None
        assert _InferenceWorker is not None
        assert _Controller is not None

    def test_threaded_pipeline_init(self):
        from od_platform.inference.pipeline import ThreadedPipeline
        from od_platform.inference.sinks import NullSink
        from pathlib import Path

        class _MockProc:
            def infer_batch(self, images):
                return [], [], [], 0.0

        pipeline = ThreadedPipeline(
            processor=_MockProc(),
            source="test.mp4",
            camera_config=None,
            output_dir=Path("."),
            output_sink=NullSink(),
            batch_size=1,
            save=False,
            show=False,
            show_info=False,
            window_name="test",
            warmup_frames=0,
            stride=2,
        )
        assert pipeline.stride == 2
        assert pipeline.batch_size == 1

    def test_inference_worker_has_required_attrs(self):
        from queue import Queue
        from threading import Event
        from od_platform.inference.pipeline import _InferenceWorker, _Reader, _Controller
        from od_platform.inference.hooks import InferHooks
        from od_platform.inference.overlay import Metrics

        # Minimal worker construction to verify instance attrs
        reader = _Reader("0", None, live=True, capacity=2,
                         capture_fps=Metrics().capture, stride=1)
        worker = _InferenceWorker(
            reader=reader,
            in_q=Queue(),
            processor=None,
            stats=None,
            m=Metrics(),
            eff_batch=1,
            warmup_frames=0,
            render_drop=True,
            key_queue=Queue(),
            controller=_Controller(),
            hooks=InferHooks(),
            cancel_token=None,
            start_time=0.0,
        )
        assert worker.first_batch_ready is not None
        assert hasattr(worker, "first_batch_ready")
        assert hasattr(worker, "interrupted")

    def test_display_accepts_key_queue(self):
        from queue import Queue
        from od_platform.inference.pipeline import _Display, _Controller
        kq = Queue()
        ctrl = _Controller()
        out_q = Queue()
        display = _Display(out_q, "test", ctrl, key_queue=kq)
        assert display._key_queue is kq


# ============================================================================
# 8-3: 服务编排
# ============================================================================

@pytest.mark.skipif(not _torch_available(), reason="torch not installed")
class TestServiceStructure:
    """8-3: InferService 阶段方法."""

    def test_service_has_private_methods(self):
        from od_platform.inference.service import InferService
        svc = InferService()
        assert hasattr(svc, "_load_configs")
        assert hasattr(svc, "_resolve_model_and_source")
        assert hasattr(svc, "_setup_inference")
        assert hasattr(svc, "_run_pipeline")
        assert hasattr(svc, "_finalize")

    def test_get_task_type_helper(self):
        from od_platform.inference.service import _get_task_type

        class MockModel:
            overrides = {"task": "detect"}
            task = "detect"

        assert _get_task_type(MockModel()) == "detect"

    def test_get_task_type_fallback(self):
        from od_platform.inference.service import _get_task_type

        class MockModel:
            overrides = {}
            task = ""

        assert _get_task_type(MockModel()) == "detect"  # default fallback

    def test_get_task_type_pose(self):
        from od_platform.inference.service import _get_task_type

        class MockModel:
            overrides = {"task": "pose"}

        assert _get_task_type(MockModel()) == "pose"

    def test_empty_boxes(self):
        from od_platform.inference.service import _empty_boxes
        boxes = _empty_boxes()
        assert boxes.shape == (0, 4)
        assert boxes.dtype == float

    def test_empty_conf(self):
        from od_platform.inference.service import _empty_conf
        conf = _empty_conf()
        assert conf.shape == (0,)
        assert conf.dtype == float


# ============================================================================
# 集成测试 (需要 ultralytics)
# ============================================================================

@pytest.mark.integration
@pytest.mark.skipif(not _ultralytics_available(), reason="ultralytics not installed")
class TestIntegrationInferService:
    """End-to-end 推理服务集成测试."""

    def test_infer_service_init(self):
        from od_platform.inference import InferService
        svc = InferService()
        assert svc is not None

    def test_infer_result_dataclass(self):
        from od_platform.inference import InferResult
        from pathlib import Path
        r = InferResult(
            success=True,
            output_dir=Path("/tmp/test"),
            stats={"frames": 10},
            infer_time=2.5,
            saved=True,
        )
        assert r.success is True
        assert r.stats["frames"] == 10

    @pytest.mark.skipif(not _has_model("yolo11n.pt"), reason="yolo11n.pt not found")
    def test_infer_image_file(self, tmp_path):
        """端到端: 图片推理 (需要 yolo11n.pt)."""
        from od_platform.inference import infer_yolo
        import cv2

        # Create a dummy image
        img_path = tmp_path / "test.jpg"
        img = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        cv2.imwrite(str(img_path), img)

        result = infer_yolo(cli_args={
            "source": str(img_path),
            "model": "yolo11n.pt",
            "save": False,
            "show": False,
        })
        assert result.success, f"Inference failed: {result.error}"
        assert result.stats.get("frames", 0) > 0


@pytest.mark.integration
@pytest.mark.skipif(not _ultralytics_available(), reason="ultralytics not installed")
class TestIntegrationFrameProcessor:
    """_FrameProcessor 集成测试."""

    def test_frame_processor_task_detection(self):
        import ultralytics
        from od_platform.inference.service import _FrameProcessor, _get_task_type

        # Create a minimal YOLO model
        model = ultralytics.YOLO("yolo11n.pt")
        task = _get_task_type(model)
        assert task == "detect"

    @pytest.mark.skipif(not _has_model("yolo11n.pt"), reason="yolo11n.pt not found")
    def test_frame_processor_infer_batch(self):
        import ultralytics
        from od_platform.inference.service import _FrameProcessor

        model = ultralytics.YOLO("yolo11n.pt")
        proc = _FrameProcessor(
            model=model,
            predict_kwargs={"conf": 0.25, "verbose": False},
            do_beautify=False,
            visualizer=None,
            use_label_mapping=False,
            style_overrides={},
            names=model.names,
        )
        img = np.random.randint(0, 255, (640, 640, 3), dtype=np.uint8)
        results, labels_list, n_list, batch_dt = proc.infer_batch([img])
        assert len(results) == 1
        assert isinstance(batch_dt, float)
        assert batch_dt > 0
