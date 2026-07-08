"""image_integrity check — 逐张解码验证图像完整性 (重型, 默认关闭)。

为什么默认关: 必须逐张打开并解码图像, I/O 与 CPU 成本跟数据集体量线性增长。
关着也要报 INFO: 报告必须如实记录"哪些项【没有】被验证"。

检测项 (开启后):
    1. 0 字节文件
    2. 无法解码 / 截断 (verify + load)
    3. EXIF Orientation != 1
    4. 通道模式分布 (RGB/L/P/RGBA...)
    5. 分辨率分布

Severity:
    损坏占比 >= IMAGE_CORRUPT_ERROR_RATIO → ERROR
    任何损坏                              → WARNING
    仅 EXIF 方向 / 模式提示               → INFO
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List

from od_platform.common.constants import IMAGE_CORRUPT_ERROR_RATIO
from od_platform.data_validation.registry import (
    check, CheckContext, CheckResult, CheckSeverity,
)

PREVIEW_LIMIT = 20
_EXIF_ORIENTATION_TAG = 274


@check("image_integrity")
def validate_image_integrity(ctx: CheckContext) -> CheckResult:
    if not ctx.options.check_images:
        return CheckResult(
            name="image_integrity",
            severity=CheckSeverity.INFO,
            summary="图像完整性检查未开启 (--check-images) — 接入第三方数据时建议开启",
            details={"reason": "disabled", "enable_flag": "--check-images"},
        )

    try:
        from PIL import Image
    except ImportError:
        return CheckResult(
            name="image_integrity",
            severity=CheckSeverity.WARNING,
            summary="已请求图像完整性检查但 Pillow 未安装 (pip install pillow)",
            details={"reason": "pillow_missing"},
        )

    snap = ctx.snapshot

    corrupt: List[Dict[str, Any]] = []
    exif_rotated: List[str] = []
    total_images   = 0
    total_corrupt  = 0
    total_exif     = 0
    mode_counter:  Counter = Counter()
    size_counter:  Counter = Counter()
    min_dim: Any = None
    max_dim: Any = None

    for split, images in snap.images_per_split.items():
        for img_path in images:
            total_images += 1

            # 1. 0 字节
            try:
                if img_path.stat().st_size == 0:
                    total_corrupt += 1
                    if len(corrupt) < PREVIEW_LIMIT:
                        corrupt.append({
                            "split": split, "image": str(img_path),
                            "kind": "zero_byte",
                        })
                    continue
            except OSError as e:
                total_corrupt += 1
                if len(corrupt) < PREVIEW_LIMIT:
                    corrupt.append({
                        "split": split, "image": str(img_path),
                        "kind": "stat_failed", "error": str(e),
                    })
                continue

            # 2. verify (结构) + load (截断)
            try:
                with Image.open(img_path) as im:
                    im.verify()
                with Image.open(img_path) as im:
                    im.load()
                    w, h = im.size
                    mode = im.mode
                    try:
                        orientation = im.getexif().get(_EXIF_ORIENTATION_TAG, 1)
                    except Exception:
                        orientation = 1
            except Exception as e:
                total_corrupt += 1
                if len(corrupt) < PREVIEW_LIMIT:
                    corrupt.append({
                        "split": split, "image": str(img_path),
                        "kind": "decode_failed",
                        "error": f"{type(e).__name__}: {e}",
                    })
                continue

            # 3/4/5. 画像信息
            mode_counter[mode] += 1
            size_counter[(w, h)] += 1
            area = w * h
            if min_dim is None or area < min_dim[0] * min_dim[1]:
                min_dim = (w, h)
            if max_dim is None or area > max_dim[0] * max_dim[1]:
                max_dim = (w, h)
            if orientation != 1:
                total_exif += 1
                if len(exif_rotated) < PREVIEW_LIMIT:
                    exif_rotated.append(str(img_path))

    corrupt_ratio = total_corrupt / max(total_images, 1)
    details: Dict[str, Any] = {
        "total_images":        total_images,
        "total_corrupt":       total_corrupt,
        "corrupt_ratio":       round(corrupt_ratio, 4),
        "exif_rotated_count":  total_exif,
        "mode_distribution":   dict(mode_counter),
        "resolution_top": [
            {"size": f"{w}x{h}", "count": n}
            for (w, h), n in size_counter.most_common(10)
        ],
        "resolution_min":      f"{min_dim[0]}x{min_dim[1]}" if min_dim else None,
        "resolution_max":      f"{max_dim[0]}x{max_dim[1]}" if max_dim else None,
        "corrupt_preview":     corrupt,
        "exif_rotated_preview": exif_rotated,
        "thresholds": {"corrupt_error_at_ratio": IMAGE_CORRUPT_ERROR_RATIO},
    }

    if total_corrupt > 0:
        severity = (
            CheckSeverity.ERROR
            if corrupt_ratio >= IMAGE_CORRUPT_ERROR_RATIO
            else CheckSeverity.WARNING
        )
        summary = (
            f"{total_corrupt}/{total_images} ({corrupt_ratio:.1%}) 张图像损坏/不可解码"
            + (f"; 另有 {total_exif} 张带 EXIF 旋转标记" if total_exif else "")
        )
    elif total_exif > 0:
        severity = CheckSeverity.INFO
        summary = (
            f"图像全部可解码; {total_exif} 张带 EXIF 旋转标记 "
            f"— 不同加载器旋转行为不一, 存在框/像素错位风险, 建议落盘前归一化"
        )
    else:
        severity = CheckSeverity.PASS
        summary = f"全部 {total_images} 张图像完整可解码, 无 EXIF 旋转标记"

    return CheckResult(
        name="image_integrity",
        severity=severity,
        summary=summary,
        details=details,
    )
