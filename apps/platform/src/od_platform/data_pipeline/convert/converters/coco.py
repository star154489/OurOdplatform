"""COCO -> YOLO 转换器(detect / segment)。

优先委托 ultralytics 内置转换器(支持分割多边形);
若不可用则回退到手动 JSON 解析(仅 bbox)。
"""
from __future__ import annotations

import json
import logging
import shutil
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import List

from od_platform.common.constants import AnnotationFormat, Task
from od_platform.data_pipeline.convert.registry import ConvertOptions, register

logger = logging.getLogger(__name__)


@register(AnnotationFormat.COCO, supported_tasks=(Task.DETECT, Task.SEGMENT))
def convert_coco(input_dir: Path, out_labels_dir: Path, options: ConvertOptions) -> List[str]:
    """COCO→YOLO:优先走 ultralytics(支持 segment),不可用时回退手动解析。"""
    out_labels_dir.mkdir(parents=True, exist_ok=True)

    json_files = sorted(input_dir.glob("*.json"))
    if not json_files:
        raise FileNotFoundError(f"在 {input_dir} 下未找到 COCO json")

    data = json.loads(json_files[0].read_text(encoding="utf-8"))
    cat_name = {c["id"]: c["name"] for c in data["categories"]}

    # 尝试 ultralytics 内置转换器(自动处理 bbox + segment)
    try:
        from ultralytics.data.converter import convert_coco as _ultra_convert

        with tempfile.TemporaryDirectory(prefix="odp_coco_") as tmp:
            tmp_labels = Path(tmp) / "labels"
            tmp_labels.mkdir()
            _ultra_convert(
                labels_dir=str(tmp_labels),
                use_segments=(options.task == Task.SEGMENT),
            )
            # 从 tmp 搬运到 out_labels_dir
            for txt in tmp_labels.glob("*.txt"):
                dst = out_labels_dir / txt.name
                if dst.exists():
                    dst.unlink()
                shutil.move(str(txt), str(dst))

        # 类别从 json categories 提取
        classes: List[str] = list(options.classes) if options.classes else []
        if not classes:
            classes = [cat_name.get(c["id"], f"class_{c['id']}") for c in sorted(data["categories"], key=lambda x: x["id"])]
        return classes

    except ImportError:
        logger.debug("ultralytics 版本不支持内置 COCO 转换,回退到手动 bbox 解析")
        return _manual_coco_convert(input_dir, out_labels_dir, options, data, cat_name)


def _manual_coco_convert(
    input_dir: Path, out_labels_dir: Path, options: ConvertOptions,
    data: dict, cat_name: dict,
) -> List[str]:
    """手动 JSON 解析(回退方案,仅 bbox)。"""
    img_info = {im["id"]: im for im in data["images"]}
    per_image = defaultdict(list)
    for ann in data["annotations"]:
        per_image[ann["image_id"]].append(ann)

    classes: List[str] = list(options.classes) if options.classes else []
    discovering = options.classes is None
    for img_id, im in img_info.items():
        W, H = float(im["width"]), float(im["height"])
        stem = im["file_name"].rsplit(".", 1)[0]
        lines: List[str] = []
        for ann in per_image.get(img_id, []):
            name = cat_name[ann["category_id"]]
            if name not in classes:
                if discovering:
                    classes.append(name)
                else:
                    continue
            cls_id = classes.index(name)
            x, y, w, h = ann["bbox"]
            lines.append(f"{cls_id} {(x + w / 2) / W:.6f} {(y + h / 2) / H:.6f} {w / W:.6f} {h / H:.6f}")
        (out_labels_dir / (stem + ".txt")).write_text("\n".join(lines), encoding="utf-8")

    return classes
