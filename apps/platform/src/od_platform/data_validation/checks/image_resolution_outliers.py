"""image_resolution_outliers check — 图像分辨率和宽高比异常检测。"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from od_platform.data_validation.registry import check, CheckContext, CheckResult, CheckSeverity

try:
    from PIL import Image
except Exception:  # pragma: no cover
    Image = None  # type: ignore[assignment]

DETAILS_PREVIEW_LIMIT = 50
DEFAULT_MIN_SIDE = 32
DEFAULT_MAX_RATIO = 6.0


def _label_for_image(image_path: Path) -> Path:
    parts = list(image_path.parts)
    for index in range(len(parts) - 1, -1, -1):
        if parts[index] == "images":
            parts[index] = "labels"
            break
    return Path(*parts[:-1]) / f"{image_path.stem}.txt"


def _safe_image_size(image_path: Path) -> Optional[Tuple[int, int]]:
    if Image is None:
        return None
    try:
        with Image.open(image_path) as image:
            return image.size
    except Exception:
        return None


def collect_image_resolution_outlier_issues(
    ctx: CheckContext,
    min_side: int = DEFAULT_MIN_SIDE,
    max_ratio: float = DEFAULT_MAX_RATIO,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    if Image is None:
        return issues, {"pillow_available": False, "reason": "未安装 Pillow，跳过分辨率扩展检测"}

    snap = ctx.snapshot
    for split, images in snap.images_per_split.items():
        labels = snap.labels_per_split.get(split, ())
        label_by_stem = {label.stem: label for label in labels}
        for image_path in images:
            label_path = label_by_stem.get(image_path.stem, _label_for_image(image_path))
            size = _safe_image_size(image_path)
            if size is None:
                issues.append({
                    "split": split,
                    "image": str(image_path),
                    "label": str(label_path),
                    "kind": "image_open_failed",
                    "detail": "无法读取图像尺寸",
                    "repair_suggestion": "用图像工具打开确认是否损坏；损坏样本需替换或删除。",
                })
                continue
            width, height = size
            short_side = min(width, height)
            long_side = max(width, height)
            if short_side < min_side:
                issues.append({
                    "split": split,
                    "image": str(image_path),
                    "label": str(label_path),
                    "kind": "low_resolution",
                    "detail": f"图像短边过小: {width}x{height}",
                    "repair_suggestion": "确认是否为误导入缩略图；建议替换为原始清晰图或删除。",
                    "width": width,
                    "height": height,
                    "min_side": min_side,
                })
            ratio = long_side / short_side if short_side else math.inf
            if ratio > max_ratio:
                issues.append({
                    "split": split,
                    "image": str(image_path),
                    "label": str(label_path),
                    "kind": "extreme_aspect_ratio",
                    "detail": f"图像宽高比异常: {width}x{height}",
                    "repair_suggestion": "核验图像是否被错误裁剪/拼接；必要时回源修复。",
                    "width": width,
                    "height": height,
                    "ratio": round(ratio, 4),
                    "max_ratio": max_ratio,
                })

    details = {
        "pillow_available": True,
        "min_side": min_side,
        "max_ratio": max_ratio,
        "issues_preview": issues[:DETAILS_PREVIEW_LIMIT],
    }
    return issues, details


@check("image_resolution_outliers")
def validate_image_resolution_outliers(ctx: CheckContext) -> CheckResult:
    issues, details = collect_image_resolution_outlier_issues(ctx)
    if not details.get("pillow_available", True):
        return CheckResult(
            name="image_resolution_outliers",
            severity=CheckSeverity.INFO,
            summary="未安装 Pillow，跳过分辨率扩展检测",
            details=details,
        )
    if not issues:
        return CheckResult(
            name="image_resolution_outliers",
            severity=CheckSeverity.PASS,
            summary="未发现分辨率异常",
            details=details,
        )
    has_open_failed = any(issue.get("kind") == "image_open_failed" for issue in issues)
    return CheckResult(
        name="image_resolution_outliers",
        severity=CheckSeverity.ERROR if has_open_failed else CheckSeverity.WARNING,
        summary=f"发现 {len(issues)} 个分辨率/宽高比异常问题",
        details=details,
    )
