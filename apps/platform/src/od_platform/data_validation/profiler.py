"""画像层 — 双轨: 明细 CSV (instances.csv + per_image.csv) + 聚合 dict (入 report.json)。

判定与画像分离:
    - check 回答"能不能训" (产 severity)
    - profiler 回答"长什么样" (产统计, 永不产 severity, 永不阻断)
"""
from __future__ import annotations

import csv
import logging
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from od_platform.common.constants import (
    BBOX_EDGE_TOLERANCE,
    BORDER_TOUCH_EPS,
    DEGENERATE_BOX_MIN_SIZE,
    SMALL_OBJECT_AREA_RATIO,
    STATS_MAX_ASPECT_RATIO,
    Task,
)
from od_platform.common.performance_utils import time_it
from od_platform.data_validation.registry import ValidationOptions
from od_platform.data_validation.snapshot import DatasetSnapshot

logger = logging.getLogger(__name__)

INSTANCE_COLUMNS = [
    "split", "image", "line_no", "class_id", "class_name",
    "cx", "cy", "w", "h", "area", "aspect_ratio",
    "img_width", "img_height", "area_px",
    "small_norm", "small_coco", "touches_border",
    "degenerate", "out_of_image", "exact_duplicate",
]
PER_IMAGE_COLUMNS = [
    "split", "image", "img_width", "img_height",
    "instances", "classes", "anomaly_instances",
]

_DENSITY_BUCKETS: List[Tuple[float, str]] = [
    (0, "0"), (1, "1"), (2, "2"), (5, "3-5"),
    (10, "6-10"), (20, "11-20"), (50, "21-50"), (math.inf, "50+"),
]


def _parse_line_geometry(
    parts: List[str], task_type: str
) -> Optional[Tuple[int, float, float, float, float]]:
    """从一行标签解析出 (class_id, cx, cy, w, h)。"""
    try:
        cls_id = int(parts[0])
    except (ValueError, IndexError):
        return None

    if task_type == Task.DETECT:
        if len(parts) != 5:
            return None
        try:
            cx, cy, w, h = (float(x) for x in parts[1:5])
        except ValueError:
            return None
        return cls_id, cx, cy, w, h

    if task_type == Task.SEGMENT:
        if len(parts) < 7 or (len(parts) - 1) % 2 != 0:
            return None
        try:
            coords = [float(x) for x in parts[1:]]
        except ValueError:
            return None
        xs, ys = coords[0::2], coords[1::2]
        x1, x2, y1, y2 = min(xs), max(xs), min(ys), max(ys)
        return cls_id, (x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1

    return None


def _instance_flags(cx: float, cy: float, w: float, h: float) -> Dict[str, bool]:
    """逐实例异常标记 — 与各 check 的判定口径严格一致 (同源 constants)。"""
    left, right = cx - w / 2, cx + w / 2
    top, bottom = cy - h / 2, cy + h / 2
    area = w * h
    overflow = max(0.0 - left, right - 1.0, 0.0 - top, bottom - 1.0)
    return {
        "degenerate": (
            w < DEGENERATE_BOX_MIN_SIZE
            or h < DEGENERATE_BOX_MIN_SIZE
            or area < DEGENERATE_BOX_MIN_SIZE ** 2
        ),
        "out_of_image": overflow > BBOX_EDGE_TOLERANCE,
        "small_norm": area < SMALL_OBJECT_AREA_RATIO,
        "touches_border": (
            left < BORDER_TOUCH_EPS or top < BORDER_TOUCH_EPS
            or right > 1.0 - BORDER_TOUCH_EPS or bottom > 1.0 - BORDER_TOUCH_EPS
        ),
    }


def _jsd(p: List[float], q: List[float]) -> float:
    """Jensen-Shannon 散度 (log2, 值域 [0,1])。"""
    def _kl(a: List[float], b: List[float]) -> float:
        return sum(
            x * math.log2(x / y) for x, y in zip(a, b) if x > 0 and y > 0
        )
    m = [(x + y) / 2 for x, y in zip(p, q)]
    return 0.5 * _kl(p, m) + 0.5 * _kl(q, m)


@time_it(name="构建数据集画像", logger_instance=logger, iterations=1)
def run_profile(
    snapshot: DatasetSnapshot,
    options: ValidationOptions,
    out_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """构建数据集画像。

    双轨:
        轨道 A: instances.csv + per_image.csv (明细)
        轨道 B: 聚合 dict (入 report.json)

    Args:
        snapshot: 数据集快照
        options:  运行开关
        out_dir:  CSV 输出目录 (None = 不写 CSV)

    Returns:
        聚合 dict (profile 字段, 直接进 report.json)
    """
    # 聚合器
    per_split_class: Dict[str, Dict[int, Dict]] = defaultdict(lambda: defaultdict(dict))
    density_counter: Counter = Counter()
    co_occurrence: Counter = Counter()
    spatial_grid: List[int] = [0] * 9
    anchor_small: List[Tuple] = []
    anchor_extreme_ar: List[Tuple] = []
    total_images = 0
    total_instances = 0
    anomaly_instances = 0
    flags_total: Counter = Counter()

    # CSV writers
    inst_writer = None
    img_writer = None
    inst_file = None
    img_file = None

    if out_dir is not None:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        inst_file = open(out_dir / "instances.csv", "w", newline="", encoding="utf-8")
        inst_writer = csv.writer(inst_file)
        inst_writer.writerow(INSTANCE_COLUMNS)
        img_file = open(out_dir / "per_image.csv", "w", newline="", encoding="utf-8")
        img_writer = csv.writer(img_file)
        img_writer.writerow(PER_IMAGE_COLUMNS)

    try:
        for split in snapshot.splits:
            images = snapshot.images_per_split.get(split, ())
            labels = snapshot.labels_per_split.get(split, ())

            for img_path, lbl_path in zip(images, labels):
                total_images += 1
                img_w, img_h = _get_image_size(img_path, options)
                line_instances = 0
                line_anomalies = 0
                line_classes: set = set()
                seen_lines: set = set()

                if not lbl_path.exists():
                    if img_writer:
                        img_writer.writerow([
                            split, str(img_path), img_w or "", img_h or "",
                            0, "", 0,
                        ])
                    continue

                try:
                    content = lbl_path.read_text(encoding="utf-8")
                except OSError:
                    continue

                for line_no, line in enumerate(content.splitlines(), 1):
                    stripped = line.strip()
                    if not stripped:
                        continue
                    total_instances += 1
                    parts = stripped.split()
                    geom = _parse_line_geometry(parts, snapshot.task_type)
                    if geom is None:
                        continue
                    cls_id, cx, cy, w, h = geom
                    area = w * h
                    ar = w / h if h > 0 else 0.0
                    flags = _instance_flags(cx, cy, w, h)
                    is_exact_dup = stripped in seen_lines
                    seen_lines.add(stripped)

                    name = snapshot.class_names[cls_id] if cls_id < len(snapshot.class_names) else f"id_{cls_id}"

                    # 聚合: per_split_class
                    pc = per_split_class[split][cls_id]
                    pc.setdefault("count", 0)
                    pc["count"] += 1
                    pc.setdefault("area_sum", 0.0)
                    pc["area_sum"] += area
                    pc.setdefault("ar_sum", 0.0)
                    pc["ar_sum"] += ar
                    pc.setdefault("small_norm", 0)
                    if flags["small_norm"]:
                        pc["small_norm"] += 1
                    pc.setdefault("touches_border", 0)
                    if flags["touches_border"]:
                        pc["touches_border"] += 1
                    pc.setdefault("degenerate_count", 0)
                    if flags["degenerate"]:
                        pc["degenerate_count"] += 1
                    pc.setdefault("out_of_image_count", 0)
                    if flags["out_of_image"]:
                        pc["out_of_image_count"] += 1

                    line_instances += 1
                    line_classes.add(cls_id)
                    if any(flags.values()) or is_exact_dup:
                        line_anomalies += 1

                    for flag, val in flags.items():
                        if val:
                            flags_total[flag] += 1
                    if is_exact_dup:
                        flags_total["exact_duplicate"] += 1

                    # 3x3 空间格
                    grid_x = min(int(cx * 3), 2)
                    grid_y = min(int(cy * 3), 2)
                    spatial_grid[grid_y * 3 + grid_x] += 1

                    # Top-N 锚点 (堆)
                    _heap_push(anchor_small, options.top_n_anomalies, area, (str(img_path), line_no, area))
                    _heap_push(anchor_extreme_ar, options.top_n_anomalies, -ar, (str(img_path), line_no, ar))

                    # CSV 行
                    if inst_writer:
                        area_px = (area * img_w * img_h) if img_w and img_h else None
                        inst_writer.writerow([
                            split, str(img_path), line_no, cls_id, name,
                            round(cx, 6), round(cy, 6), round(w, 6), round(h, 6),
                            round(area, 8), round(ar, 4),
                            img_w or "", img_h or "", round(area_px, 2) if area_px else "",
                            int(flags["small_norm"]), "", int(flags["touches_border"]),
                            int(flags["degenerate"]), int(flags["out_of_image"]), int(is_exact_dup),
                        ])

                # 密度
                density_counter[_bucket_instances(line_instances)] += 1

                # 共现
                cls_list = sorted(line_classes)
                for i in range(len(cls_list)):
                    for j in range(i + 1, len(cls_list)):
                        co_occurrence[(cls_list[i], cls_list[j])] += 1

                if img_writer:
                    img_writer.writerow([
                        split, str(img_path), img_w or "", img_h or "",
                        line_instances, len(line_classes), line_anomalies,
                    ])

        # 构建聚合结果
        profile = _build_profile(
            snapshot, per_split_class, density_counter, co_occurrence,
            spatial_grid, anchor_small, anchor_extreme_ar,
            flags_total, total_images, total_instances, anomaly_instances,
        )

        logger.info(
            f"画像构建完成: {total_images} 图 / {total_instances} 实例"
            + (f", 明细已写入 {out_dir}" if out_dir else "")
        )
        return profile

    finally:
        if inst_file:
            inst_file.close()
        if img_file:
            img_file.close()


def _get_image_size(img_path: Path, options: ValidationOptions) -> Tuple[Optional[int], Optional[int]]:
    """读图像分辨率 (仅读 header, 不解码像素)。"""
    if not options.read_image_headers:
        return None, None
    try:
        from PIL import Image
        with Image.open(img_path) as im:
            return im.size
    except Exception:
        return None, None


def _bucket_instances(n: int) -> str:
    for threshold, label in _DENSITY_BUCKETS:
        if n <= threshold:
            return label
    return "50+"


def _heap_push(heap: List, max_size: int, key: float, item: Tuple) -> None:
    heap.append((key, item))
    heap.sort(key=lambda x: x[0])
    if len(heap) > max_size:
        heap.pop()


def _build_profile(
    snapshot, per_split_class, density_counter, co_occurrence,
    spatial_grid, anchor_small, anchor_extreme_ar,
    flags_total, total_images, total_instances, anomaly_instances,
) -> Dict[str, Any]:
    """构建最终聚合 dict。"""
    # per_split_class → 可序列化
    ps_class_serial = {}
    for split, classes in per_split_class.items():
        ps_class_serial[split] = {}
        for cls_id, stats in classes.items():
            name = snapshot.class_names[cls_id] if cls_id < len(snapshot.class_names) else f"id_{cls_id}"
            count = stats.get("count", 0)
            ps_class_serial[split][name] = {
                "count":          count,
                "area_mean":      round(stats["area_sum"] / count, 6) if count else 0,
                "ar_mean":        round(stats["ar_sum"] / count, 4) if count else 0,
                "small_norm":     stats.get("small_norm", 0),
                "touches_border": stats.get("touches_border", 0),
                "degenerate":     stats.get("degenerate_count", 0),
                "out_of_image":   stats.get("out_of_image_count", 0),
            }

    # 一致性 (JSD)
    consistency = {}
    splits = snapshot.splits
    if "train" in splits:
        train_dist = _class_distribution(snapshot, "train")
        for target in ("val", "test"):
            if target not in splits:
                continue
            target_dist = _class_distribution(snapshot, target)
            if train_dist and target_dist:
                jsd_val = _jsd(train_dist, target_dist)
                consistency[f"train_vs_{target}"] = {
                    "jsd": round(jsd_val, 4),
                    "level": "一致" if jsd_val < 0.05 else "轻微偏差" if jsd_val < 0.15 else "显著偏差",
                }

    return {
        "per_split_class": ps_class_serial,
        "density": dict(density_counter),
        "co_occurrence": [
            {"classes": [snapshot.class_names[a] if a < len(snapshot.class_names) else f"id_{a}",
                          snapshot.class_names[b] if b < len(snapshot.class_names) else f"id_{b}"],
             "count": n}
            for (a, b), n in co_occurrence.most_common(20)
        ],
        "spatial_grid": spatial_grid,
        "anomaly_anchors": {
            "smallest_areas": [{"image": str(item[0]), "line": item[1], "area": round(item[2], 6)}
                                for _, item in anchor_small[:10]],
            "extreme_aspect_ratios": [{"image": str(item[0]), "line": item[1], "ar": round(item[2], 4)}
                                       for _, item in anchor_extreme_ar[:10]],
        },
        "flags_total": dict(flags_total),
        "consistency": consistency,
        "generated": True,
    }


def _class_distribution(snapshot: DatasetSnapshot, split: str) -> List[float]:
    st = snapshot.stats_per_split.get(split)
    if st is None or not st.class_instances:
        return []
    total = sum(st.class_instances.values())
    if total == 0:
        return []
    return [st.class_instances.get(cid, 0) / total for cid in range(snapshot.nc)] if snapshot.nc else []
