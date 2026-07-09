"""YOLO -> YOLO 直通转换器(detect / segment)。

"直通"的意思:源数据已经是 YOLO 格式,不需要任何坐标换算,只需把散落的 .txt 搬到
统一的输出目录。这是"接口相同、行为却不同"的典型 —— 它和 voc/coco 签名一致,但内部
什么都不解析。

⚠️ --classes 在这里的边界(重要,务必讲清):
    yolo 的 txt 每行只有数字 class_id、不含类名。所以 options.classes 在这里是
    【必填的命名信息】(没有它就没法写 yaml 的 names),而【不是过滤器】。
    本转换器原样搬运、不改内容、不重映射 id;因此对 yolo 源数据"删类"无法走 --classes
    —— 那样只会让 yaml 的 names 与 txt 里的 id 对不上(越界 / 张冠李戴)。
    yolo 源要删类,只能在源头重写 txt。
"""
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import List

from od_platform.common.constants import AnnotationFormat, Task
from od_platform.data_pipeline.convert.registry import ConvertOptions, register

logger = logging.getLogger(__name__)


def _validate_yolo_txts(txt_files: list, nc: int) -> None:
    """逐行校验 YOLO txt:字段数/class_id/坐标范围,发现问题直接抛 ValueError。"""
    for txt in txt_files:
        for line_no, line in enumerate(txt.read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) != 5:
                raise ValueError(f"{txt.name}:{line_no} 字段数={len(parts)},期望5")
            try:
                cls_id = int(parts[0])
                cx, cy, w, h = float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
            except ValueError:
                raise ValueError(f"{txt.name}:{line_no} 无法解析为数字: {line[:80]}")
            if nc > 0 and not (0 <= cls_id < nc):
                raise ValueError(
                    f"{txt.name}:{line_no} class_id={cls_id} 越界 [0,{nc})"
                )
            if not (0.0 <= cx <= 1.0 and 0.0 <= cy <= 1.0 and 0.0 <= w <= 1.0 and 0.0 <= h <= 1.0):
                raise ValueError(
                    f"{txt.name}:{line_no} 坐标不在[0,1]: {line[:80]}"
                )


@register(AnnotationFormat.YOLO, supported_tasks=(Task.DETECT, Task.SEGMENT))
def convert_yolo(input_dir: Path, output_labels_dir: Path, options: ConvertOptions) -> List[str]:
    if not options.classes:
        # yolo 不含类名,必须由用户显式给出类别顺序,否则 yaml 的 names 无从填起。
        raise ValueError("yolo 格式不含类别名信息,必须通过 options.classes 显式提供类别顺序。")

    txt_files = sorted(input_dir.glob("*.txt"))
    if not txt_files:
        raise FileNotFoundError(f"在 {input_dir} 下未找到任何 yolo txt")

    output_labels_dir.mkdir(parents=True, exist_ok=True)
    # 直通前校验:字段数/class_id/坐标范围
    nc = len(options.classes)
    _validate_yolo_txts(txt_files, nc)
    for txt in txt_files:
        dst = output_labels_dir / txt.name
        try:                                    # 优先硬链接(零拷贝、省磁盘);跨盘会失败
            if dst.exists():
                dst.unlink()
            os.link(txt, dst)
        except OSError:                         # 跨文件系统等情况:退回普通复制
            shutil.copy2(txt, dst)

    logger.info("YOLO 直通: %d 个 txt 就位, %d 个类别", len(txt_files), len(options.classes))
    return list(options.classes)
