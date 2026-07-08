#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :orchestrator.py
# @Function  :编排器 —— DatasetPipeline.run() 穿起整条流水线
"""DatasetPipeline:转换 → 报告 → 划分 → 落盘 → yaml,一条命令串到底。"""
from __future__ import annotations

import logging
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from od_platform.common import paths
from od_platform.common.constants import (
    COVERAGE_HARD_THRESHOLD, COVERAGE_SOFT_THRESHOLD, DEFAULT_RANDOM_STATE, DEFAULT_SPLIT_STRATEGY,
    IMAGE_EXTENSIONS, AnnotationFormat, Task
)
from od_platform.common.refs import resolve_dataset
from od_platform.common.paths import dataset_processed_dir, dataset_yaml_path
from od_platform.data_pipeline.convert.registry import ConvertOptions, get_converter
from od_platform.data_pipeline.convert.service import convert_data_to_yolo
from od_platform.data_pipeline.report import analyze_class_balance, render_balance_report
from od_platform.data_pipeline.split.manifest import PairList
from od_platform.data_pipeline.split.materializer import SplitOutputDirs, materialize
from od_platform.data_pipeline.split.split_service import split_pairs
from od_platform.data_pipeline.split.yaml_writer import write_dataset_yaml

logger = logging.getLogger(__name__)

_PIPELINE_LOG_SETUP = False


def _setup_pipeline_log() -> None:
    """首次调用时在 LOGGING_DIR 下创建 transform_<timestamp>.log，后续日志同时写文件。"""
    global _PIPELINE_LOG_SETUP
    if _PIPELINE_LOG_SETUP:
        return
    _PIPELINE_LOG_SETUP = True

    log_dir = paths.LOGGING_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"transform_{ts}.log"

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    fh = logging.FileHandler(log_path, encoding="utf-8", mode="w")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    root.addHandler(fh)
    logger.info("流水线日志: %s", log_path)


class DatasetPipeline:
    """一次"把某数据集转换 + 划分成可训练数据集"的完整流程。"""

    def __init__(
        self, dataset: str, annotation_format: str, *,
        task: str = Task.DETECT, train_rate: float = 0.8, val_rate: float = 0.1,
        classes: Optional[List[str]] = None, random_state: int = DEFAULT_RANDOM_STATE,
        split_strategy: str = DEFAULT_SPLIT_STRATEGY,
    ):
        self.annotation_format = annotation_format
        self.task = task
        self.train_rate = train_rate
        self.val_rate = val_rate
        self.random_state = random_state
        self.split_strategy = split_strategy
        self._options = ConvertOptions(task=task, classes=classes)

        self.raw_root = resolve_dataset(dataset)
        self.dataset_name = self.raw_root.name
        self.raw_images = self.raw_root / "images"
        self.raw_annotations = self.raw_root / "annotations"
        self.processed_root = dataset_processed_dir(self.dataset_name)
        self.output_dirs = SplitOutputDirs.for_dataset_root(self.processed_root)
        self.yaml_out = dataset_yaml_path(self.dataset_name)

    def run(self) -> Dict:
        _setup_pipeline_log()
        logger.info("数据集流水线启动: %s (format=%s, task=%s, split=%s)",
                    self.dataset_name, self.annotation_format, self.task, self.split_strategy)
        self._check_raw()

        entry = get_converter(self.annotation_format)
        if not entry.supports(self.task):
            raise ValueError(f"格式 {self.annotation_format!r} 不支持 task={self.task!r}。支持: {entry.supported_tasks}")

        with tempfile.TemporaryDirectory(prefix="odp_pipe_") as tmp:
            staging = Path(tmp) / "labels"
            classes = convert_data_to_yolo(self.raw_annotations, staging, self.annotation_format, self._options)
            pairs = self._pair_images_with_labels(staging)
            labels_per_image = self._build_labels_per_image(pairs, classes)

            report = analyze_class_balance(labels_per_image, classes, self.train_rate, self.val_rate)
            for line, is_warning in render_balance_report(report, self.annotation_format):
                (logger.warning if is_warning else logger.info)(line)

            manifest = split_pairs(
                pairs, train_rate=self.train_rate, val_rate=self.val_rate,
                random_state=self.random_state, strategy=self.split_strategy,
                labels_per_image=labels_per_image,
            )
            counts = materialize(manifest, self.output_dirs)
            write_dataset_yaml(
                self.yaml_out, dataset_root=self.processed_root, classes=classes,
                manifest=manifest, dataset_name=self.dataset_name,
                source_format=self.annotation_format, task=self.task,
            )

        logger.info("流水线完成: 划分=%s, yaml=%s", counts, self.yaml_out)
        return {"counts": counts, "yaml": str(self.yaml_out)}

    def _check_raw(self) -> None:
        if not self.raw_root.is_dir():
            raise FileNotFoundError(f"数据集目录不存在: {self.raw_root}")
        if not self.raw_images.is_dir():
            raise FileNotFoundError(f"缺少 images 子目录: {self.raw_images}")
        if not self.raw_annotations.is_dir():
            raise FileNotFoundError(f"缺少 annotations 子目录: {self.raw_annotations}")
        self._check_coverage()

    def _check_coverage(self) -> None:
        n_images = sum(len(list(self.raw_images.glob(f"*{ext}"))) for ext in IMAGE_EXTENSIONS)
        if n_images == 0:
            raise FileNotFoundError(f"{self.raw_images} 下没有任何图像")
        if self.annotation_format == AnnotationFormat.COCO:
            logger.debug("COCO 跳过 stem 覆盖率检查")
            return
        n_annos = len(list(self.raw_annotations.glob("*.*")))
        coverage = n_annos / n_images
        logger.info("覆盖率: %d/%d = %.1f%%", n_annos, n_images, coverage * 100)
        if coverage < COVERAGE_HARD_THRESHOLD:
            raise ValueError(
                f"图像-标注覆盖率 {coverage:.1%} 低于硬阈值 {COVERAGE_HARD_THRESHOLD:.0%},"
                f"终止以免训练失败(总图像 {n_images}, 有标注 {n_annos})。请检查 annotations/ 或确认 --format。"
            )
        if coverage < COVERAGE_SOFT_THRESHOLD:
            logger.warning("覆盖率 %.1f%% 低于软阈值 %.0f%%,可继续但建议核对。",
                        coverage * 100, COVERAGE_SOFT_THRESHOLD * 100)

    def _pair_images_with_labels(self, labels_dir: Path) -> PairList:
        image_index = {}
        for ext in IMAGE_EXTENSIONS:
            for img in self.raw_images.glob(f"*{ext}"):
                image_index[img.stem] = img
        pairs: PairList = []
        for lbl in sorted(labels_dir.glob("*.txt")):
            img = image_index.get(lbl.stem)
            if img is not None:
                pairs.append((img, lbl))
        return pairs

    def _build_labels_per_image(self, pairs: PairList, classes: List[str]) -> Dict[str, List[str]]:
        result: Dict[str, List[str]] = {}
        for img_path, label_path in pairs:
            names: List[str] = []
            if label_path.exists():
                for line in label_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line:
                        cls_id = int(line.split()[0])
                        if 0 <= cls_id < len(classes):
                            names.append(classes[cls_id])
            result[img_path.stem] = names
        return result
