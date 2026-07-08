"""D5 runtime_config & D3 data_pipeline 核心测试。"""
from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "apps" / "platform" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


# ---------- constants ----------

class TestConstants:
    def test_task_values(self):
        from od_platform.common.constants import Task
        assert "detect" in Task.all()
        assert "segment" in Task.all()

    def test_annotation_format_values(self):
        from od_platform.common.constants import AnnotationFormat
        assert "pascal_voc" in AnnotationFormat.all()
        assert "coco" in AnnotationFormat.all()
        assert "yolo" in AnnotationFormat.all()

    def test_split_strategy(self):
        from od_platform.common.constants import SplitStrategy
        assert "random" in SplitStrategy.all()
        assert "stratified" in SplitStrategy.all()


# ---------- SplitManifest ----------

class TestSplitManifest:
    def test_empty(self):
        from od_platform.data_pipeline.split.manifest import SplitManifest
        m = SplitManifest()
        assert m.total == 0
        s = m.summary()
        assert s["total"] == 0

    def test_counts(self):
        from od_platform.data_pipeline.split.manifest import SplitManifest
        from pathlib import Path
        m = SplitManifest(
            train=[(Path("a.jpg"), Path("a.txt"))],
            val=[(Path("b.jpg"), Path("b.txt"))],
        )
        assert m.total == 2
        assert m.summary()["train"] == 1
        assert m.summary()["val"] == 1
        assert m.summary()["test"] == 0


# ---------- random_split ----------

class TestRandomSplit:
    def test_basic_split(self):
        from od_platform.data_pipeline.split.manifest import SplitManifest
        from od_platform.data_pipeline.split.strategy_registry import SplitOptions
        from od_platform.data_pipeline.split.split_service import split_pairs
        from pathlib import Path

        pairs = [(Path(f"{i}.jpg"), Path(f"{i}.txt")) for i in range(100)]
        result = split_pairs(pairs, "random", SplitOptions(train_rate=0.8, val_rate=0.1))
        assert result.total == 100
        assert len(result.train) == 80
        assert len(result.val) == 10
        assert len(result.test) == 10

    def test_reproducible_seed(self):
        from od_platform.data_pipeline.split.strategy_registry import SplitOptions
        from od_platform.data_pipeline.split.split_service import split_pairs
        from pathlib import Path

        pairs = [(Path(f"{i}.jpg"), Path(f"{i}.txt")) for i in range(100)]
        r1 = split_pairs(pairs, "random", SplitOptions(random_state=42))
        r2 = split_pairs(pairs, "random", SplitOptions(random_state=42))
        assert [p[0].name for p in r1.train] == [p[0].name for p in r2.train]


# ---------- YOLOTrainConfig ----------

class TestYOLOTrainConfig:
    def test_default_config(self):
        from od_platform.runtime_config.train import YOLOTrainConfig
        cfg = YOLOTrainConfig()
        assert cfg.epochs == 100
        assert cfg.batch == 16
        assert cfg.imgsz == 640
        assert cfg.task == "detect"

    def test_task_validation(self):
        from od_platform.runtime_config.train import YOLOTrainConfig
        import pytest
        with pytest.raises(Exception):
            YOLOTrainConfig(task="invalid_task")

    def test_experiment_name(self):
        from od_platform.runtime_config.train import YOLOTrainConfig
        cfg = YOLOTrainConfig(experiment_name="my_exp")
        assert cfg.experiment_name == "my_exp"

    def test_epochs_ge_1(self):
        from od_platform.runtime_config.train import YOLOTrainConfig
        import pytest
        with pytest.raises(Exception):
            YOLOTrainConfig(epochs=0)

    def test_lr0_gt_0(self):
        from od_platform.runtime_config.train import YOLOTrainConfig
        import pytest
        with pytest.raises(Exception):
            YOLOTrainConfig(lr0=0)

    def test_to_ultralytics_kwargs(self):
        from od_platform.runtime_config.train import YOLOTrainConfig
        cfg = YOLOTrainConfig(epochs=50, lr0=0.001)
        kwargs = cfg.to_ultralytics_kwargs()
        assert kwargs["epochs"] == 50
        assert kwargs["lr0"] == 0.001
        assert "experiment_name" not in kwargs  # framework-only field
        assert "verbose" not in kwargs          # framework-only
