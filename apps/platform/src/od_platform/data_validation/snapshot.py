#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  : snapshot.py
# @Function  : DatasetSnapshot — 一次扫描, 多次复用
"""DatasetSnapshot — 一次扫描, 多次复用。

设计原则:
    - 装数据, 不做判断 (业务判断属于 check 函数)
    - frozen=True 防止 check 串改造成调试灾难
    - best-effort: yaml 解析失败 / split 目录不存在都不抛, 装进 snapshot
      让 check 自己拿去判定 — 调度层永远不该自己 fail
    - 顺手统计: 同一循环白拿的 per-class counts, 零额外 I/O
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from od_platform.common.constants import IMAGE_EXTENSIONS, Task
from od_platform.common.performance_utils import time_it

logger = logging.getLogger(__name__)


# ============================================================
# SplitStats — 轻量统计
# ============================================================

@dataclass(frozen=True)
class SplitStats:
    """单个 split 的轻量统计 — 供 ValidationReport 数据集摘要。"""
    image_count:     int    # 该 split 的图像总数
    annotated_count: int    # 有非空标签的图像数
    total_instances: int    # 全部 bbox 实例数
    class_instances: Dict[int, int] = field(default_factory=dict)  # {class_id: 实例数}
    class_images:    Dict[int, int] = field(default_factory=dict)  # {class_id: 含该类的图像数}


# ============================================================
# DatasetSnapshot — 不可变数据载体
# ============================================================

@dataclass(frozen=True)
class DatasetSnapshot:
    """对一个数据集做一次完整快照, 供所有 check 共享消费。

    所有路径已经解析为绝对路径。
    """
    yaml_path:        Path
    yaml_data:        Dict[str, Any]
    yaml_load_error:  Optional[str]          # None = 解析成功
    data_root:        Path                   # 数据集根目录
    nc:               Optional[int]          # 类别数 (缺失或非法时 None)
    class_names:      Tuple[str, ...]        # 类别名 (按 ID 升序)
    task_type:        str                    # 'detect' / 'segment'
    images_per_split: Dict[str, Tuple[Path, ...]]   # {split: (图像绝对路径, ...)}
    labels_per_split: Dict[str, Tuple[Path, ...]]   # {split: (期望标签路径, ...)}  图→标签方向
    stats_per_split:  Dict[str, SplitStats]
    label_files_per_split: Dict[str, Tuple[Path, ...]] = field(default_factory=dict)
    """{split: labels 目录下【实际存在】的 .txt 文件} — 标签→图方向, 供 orphan_labels 用。"""
    scan_warnings:    Tuple[str, ...] = field(default_factory=tuple)

    # ---------- 派生属性 ----------

    @property
    def splits(self) -> Tuple[str, ...]:
        order = ("train", "val", "test")
        return tuple(s for s in order if s in self.images_per_split)

    @property
    def total_images(self) -> int:
        return sum(len(imgs) for imgs in self.images_per_split.values())


# ============================================================
# 内部辅助 — IO / 解析 (失败不抛)
# ============================================================

def _load_yaml(yaml_path: Path) -> Tuple[Dict[str, Any], Optional[str]]:
    if not yaml_path.exists():
        return {}, f"yaml 文件不存在: {yaml_path}"
    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            return {}, f"yaml 顶层不是 dict: {type(data).__name__}"
        return data, None
    except yaml.YAMLError as e:
        return {}, f"yaml 解析失败: {e}"
    except OSError as e:
        return {}, f"yaml 读取失败: {e}"


def _resolve_data_root(yaml_path: Path, yaml_data: Dict[str, Any]) -> Path:
    path_str = yaml_data.get("path")
    if not path_str:
        return yaml_path.parent.resolve()
    p = Path(path_str)
    return p.resolve() if p.is_absolute() else (yaml_path.parent / p).resolve()


def _resolve_split_dir(data_root: Path, split_field: Any) -> Optional[Path]:
    if not isinstance(split_field, str) or not split_field.strip():
        return None
    p = Path(split_field)
    return p.resolve() if p.is_absolute() else (data_root / p).resolve()


def _list_images(split_dir: Path) -> List[Path]:
    if not split_dir.exists() or not split_dir.is_dir():
        return []
    images: List[Path] = []
    for ext in IMAGE_EXTENSIONS:
        images.extend(split_dir.glob(f"*{ext}"))
        images.extend(split_dir.glob(f"*{ext.upper()}"))
    return sorted(set(images))


def _label_path_for_image(image_path: Path) -> Path:
    """倒着找最后一个 'images' 替换为 'labels'。"""
    parts = list(image_path.parts)
    for i in range(len(parts) - 1, -1, -1):
        if parts[i] == "images":
            parts[i] = "labels"
            break
    return Path(*parts[:-1]) / (image_path.stem + ".txt")


def _normalize_names(names_raw: Any) -> Tuple[str, ...]:
    if isinstance(names_raw, list):
        if all(isinstance(n, str) for n in names_raw):
            return tuple(names_raw)
        return ()
    if isinstance(names_raw, dict):
        if all(isinstance(k, int) for k in names_raw) and all(isinstance(v, str) for v in names_raw.values()):
            return tuple(v for _, v in sorted(names_raw.items()))
        return ()
    return ()


def _build_split_stats(labels: List[Path]) -> SplitStats:
    image_count = len(labels)
    annotated_count = 0
    total_instances = 0
    class_instances: Dict[int, int] = {}
    class_images: Dict[int, int] = {}

    for lbl in labels:
        if not lbl.exists():
            continue
        try:
            content = lbl.read_text(encoding="utf-8")
        except OSError:
            continue
        lines = [l for l in content.splitlines() if l.strip()]
        if not lines:
            continue
        annotated_count += 1
        total_instances += len(lines)

        seen_in_image: set = set()
        for line in lines:
            parts = line.split()
            if not parts:
                continue
            try:
                cls_id = int(parts[0])
            except ValueError:
                continue
            class_instances[cls_id] = class_instances.get(cls_id, 0) + 1
            if cls_id not in seen_in_image:
                seen_in_image.add(cls_id)
                class_images[cls_id] = class_images.get(cls_id, 0) + 1

    return SplitStats(
        image_count=image_count,
        annotated_count=annotated_count,
        total_instances=total_instances,
        class_instances=class_instances,
        class_images=class_images,
    )


def _list_label_files(labels: List[Path]) -> Tuple[Path, ...]:
    if not labels:
        return ()
    labels_dir = labels[0].parent
    if not labels_dir.exists() or not labels_dir.is_dir():
        return ()
    found = set(labels_dir.glob("*.txt")) | set(labels_dir.glob("*.TXT"))
    return tuple(sorted(found))


# ============================================================
# 公开 API: build_snapshot
# ============================================================

@time_it(name="构建数据集快照", logger_instance=logger, iterations=1)
def build_snapshot(
    yaml_path: Path,
    task_type: Optional[str] = None,
) -> DatasetSnapshot:
    """构造数据集快照, 一次扫描提供后续 check 全部所需素材。

    best-effort — 解析失败 / 目录不存在只装进 warnings, 不抛异常。
    """
    yaml_path = yaml_path.resolve()
    warnings: List[str] = []

    yaml_data, yaml_err = _load_yaml(yaml_path)
    if yaml_err:
        warnings.append(yaml_err)

    data_root = _resolve_data_root(yaml_path, yaml_data)

    nc = yaml_data.get("nc") if isinstance(yaml_data.get("nc"), int) else None
    class_names = _normalize_names(yaml_data.get("names"))

    resolved_task = task_type or yaml_data.get("task") or Task.DETECT
    if resolved_task not in (Task.DETECT, Task.SEGMENT):
        warnings.append(f"未知 task_type '{resolved_task}', 回退到 '{Task.DETECT}'")
        resolved_task = Task.DETECT

    images_per_split: Dict[str, Tuple[Path, ...]] = {}
    labels_per_split: Dict[str, Tuple[Path, ...]] = {}
    stats_per_split:  Dict[str, SplitStats] = {}
    label_files_per_split: Dict[str, Tuple[Path, ...]] = {}

    for split in ("train", "val", "test"):
        split_dir = _resolve_split_dir(data_root, yaml_data.get(split))
        if split_dir is None or not split_dir.exists():
            if split in yaml_data:
                warnings.append(f"split '{split}' 目录不可用: {split_dir}")
            continue

        images = _list_images(split_dir)
        if not images:
            warnings.append(f"split '{split}' 目录下无图像: {split_dir}")
            continue

        labels = [_label_path_for_image(img) for img in images]
        images_per_split[split] = tuple(images)
        labels_per_split[split] = tuple(labels)
        stats_per_split[split] = _build_split_stats(labels)
        label_files_per_split[split] = _list_label_files(labels)

    snapshot = DatasetSnapshot(
        yaml_path=yaml_path,
        yaml_data=yaml_data,
        yaml_load_error=yaml_err,
        data_root=data_root,
        nc=nc,
        class_names=class_names,
        task_type=resolved_task,
        images_per_split=images_per_split,
        labels_per_split=labels_per_split,
        stats_per_split=stats_per_split,
        label_files_per_split=label_files_per_split,
        scan_warnings=tuple(warnings),
    )
    logger.info(
        "snapshot 构建完成: %d 张图像, splits=%s, task=%s",
        snapshot.total_images, list(snapshot.splits), resolved_task,
    )
    return snapshot
