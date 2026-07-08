"""编排器：将转换 → 配对 → 报告 → 划分 → 落盘 → yaml 串成完整流水线。"""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from od_platform.common.constants import (
    COVERAGE_HARD_THRESHOLD,
    DEFAULT_RANDOM_STATE,
    DEFAULT_SPLIT_STRATEGY,
    IMAGE_EXTENSIONS,
    SplitStrategy,
)
from od_platform.common.paths import (
    DATASET_CONFIGS_DIR,
    RAW_DATA_DIR,
    dataset_processed_dir,
    dataset_yaml_path,
)
from od_platform.data_pipeline.convert.registry import ConvertOptions
from od_platform.data_pipeline.convert.service import convert_data_to_yolo
from od_platform.data_pipeline.report import analyze_class_balance
from od_platform.data_pipeline.split.materializer import (
    SplitOutputDirs,
    materialize,
)
from od_platform.data_pipeline.split.split_service import split_pairs
from od_platform.data_pipeline.split.strategy_registry import SplitOptions
from od_platform.data_pipeline.split.yaml_writer import write_dataset_yaml

logger = logging.getLogger(__name__)


class DatasetPipeline:
    """数据流水线编排器 —— 一次完整的数据集转换与划分。

    Usage:
        pipe = DatasetPipeline("safety_helmet", "pascal_voc")
        result = pipe.run()
    """

    def __init__(
        self,
        dataset: str,
        annotation_format: str,
        *,
        task: str = "detect",
        train_rate: float = 0.8,
        val_rate: float = 0.1,
        classes: Optional[List[str]] = None,
        random_state: int = DEFAULT_RANDOM_STATE,
        split_strategy: str = DEFAULT_SPLIT_STRATEGY,
    ):
        self.dataset = dataset
        self.annotation_format = annotation_format
        self.task = task
        self.train_rate = train_rate
        self.val_rate = val_rate
        self.classes = classes
        self.random_state = random_state
        self.split_strategy = split_strategy

        # 计算路径
        self.raw_dir = RAW_DATA_DIR / dataset
        self.images_dir = self.raw_dir / "images"
        self.annotations_dir = self.raw_dir / "annotations"
        self.output_root = dataset_processed_dir(dataset)
        self.yaml_path = dataset_yaml_path(dataset)

    def run(self) -> dict:
        """执行完整流水线。"""
        # ── 1. 检查原始数据 ──────────────────────────────────
        logger.info("数据集: %s, 格式: %s, 策略: %s",
                     self.dataset, self.annotation_format, self.split_strategy)
        self._check_raw()

        # ── 2. 转换: 标注 → YOLO txt ──────────────────────────
        with tempfile.TemporaryDirectory(prefix=f"odp_{self.dataset}_") as tmp:
            tmp_dir = Path(tmp)
            labels_dir = tmp_dir / "labels"
            convert_opts = ConvertOptions(task=self.task, classes=self.classes)
            class_names = convert_data_to_yolo(
                self.annotations_dir, labels_dir, self.annotation_format, convert_opts,
            )
            logger.info("转换完成, 类别: %s", class_names)

            # ── 3. 配对图像与标注 ──────────────────────────────
            pairs = self._pair_images_with_labels(labels_dir)

            # ── 4. 构建 labels_per_image (用于报告 + 分层策略)─
            labels_per_image = self._build_labels_per_image(pairs)

            # ── 5. 类别平衡报告 ────────────────────────────────
            report = analyze_class_balance(
                labels_per_image, len(pairs), len(pairs),
            )
            report.print()

            # ── 6. 划分 ────────────────────────────────────────
            split_opts = SplitOptions(
                train_rate=self.train_rate,
                val_rate=self.val_rate,
                random_state=self.random_state,
                labels_per_image=labels_per_image
                if self.split_strategy != SplitStrategy.RANDOM else None,
            )
            manifest = split_pairs(pairs, self.split_strategy, split_opts)
            logger.info("划分结果: %s", manifest.summary())

            # ── 7. 物化 ────────────────────────────────────────
            output_dirs = SplitOutputDirs.for_dataset_root(self.output_root)
            materialize(manifest, output_dirs)
            logger.info("物化完成: %s", self.output_root)

            # ── 8. 写 yaml ─────────────────────────────────────
            write_dataset_yaml(self.yaml_path, class_names, output_dirs)
            logger.info("yaml 已生成: %s", self.yaml_path)

        return {
            "counts": manifest.summary(),
            "yaml": str(self.yaml_path),
            "classes": class_names,
        }

    def _check_raw(self) -> None:
        """预检查:原始数据目录存在且非空。"""
        if not self.raw_dir.exists():
            raise FileNotFoundError(
                f"原始数据目录不存在: {self.raw_dir}。"
                f"请将数据集放入 data/raw/<dataset_name>/{{images/, annotations/}}"
            )
        if not self.images_dir.exists() or not self.annotations_dir.exists():
            raise FileNotFoundError(
                f"数据集 {self.dataset} 缺少 images/ 或 annotations/ 子目录"
            )

    def _pair_images_with_labels(
        self, labels_dir: Path,
    ) -> List[Tuple[Path, Path]]:
        """按 stem 配对图像和标签文件。"""
        # 建立 stem → label_path 索引
        label_map: Dict[str, Path] = {}
        for lbl in labels_dir.glob("*.txt"):
            label_map[lbl.stem] = lbl

        pairs: List[Tuple[Path, Path]] = []
        for img in sorted(self.images_dir.iterdir()):
            if img.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            stem = img.stem
            if stem in label_map:
                pairs.append((img, label_map[stem]))

        # 覆盖率检查
        coverage = len(pairs) / len(label_map) if label_map else 1.0
        if coverage < COVERAGE_HARD_THRESHOLD:
            logger.warning(
                "覆盖率过低: %.1f%% 的标注找到了对应图像 (%d/%d)。"
                "检查 images/ 是否缺少文件。",
                coverage * 100, len(pairs), len(label_map),
            )

        logger.info("配对: %d 对 (图 %d, 标注 %d)",
                     len(pairs), len(list(self.images_dir.iterdir())), len(label_map))
        return pairs

    @staticmethod
    def _build_labels_per_image(
        pairs: List[Tuple[Path, Path]],
    ) -> Dict[str, List[str]]:
        """从已配对的列表还原 {图像路径: [类别名]}。

        注意:这里读的是 YOLO txt,只有 class_id(数字),
        无法还原原始类名。所以 labels_per_image 以路径字符串为键。
        分层策略若要使用 labels_per_image,需要另行传入类别映射。
        """
        result: Dict[str, List[str]] = {}
        for img_path, lbl_path in pairs:
            class_ids: List[str] = []
            if lbl_path.exists():
                for line in lbl_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line:
                        class_ids.append(line.split()[0])
            result[str(img_path)] = class_ids
        return result
