"""bbox_size_outliers check — 极小/极大目标框面积检测。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from od_platform.data_validation.registry import check, CheckContext, CheckResult, CheckSeverity

DETAILS_PREVIEW_LIMIT = 50
DEFAULT_TINY_AREA = 0.0001
DEFAULT_HUGE_AREA = 0.85


def _label_for_image(image_path: Path) -> Path:
    parts = list(image_path.parts)
    for index in range(len(parts) - 1, -1, -1):
        if parts[index] == "images":
            parts[index] = "labels"
            break
    return Path(*parts[:-1]) / f"{image_path.stem}.txt"


def _parse_yolo_boxes(label_path: Path) -> List[Tuple[int, float, float, float, float, int]]:
    boxes: List[Tuple[int, float, float, float, float, int]] = []
    if not label_path.exists():
        return boxes
    try:
        lines = label_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return boxes
    for line_no, line in enumerate(lines, 1):
        parts = line.split()
        if len(parts) != 5:
            continue
        try:
            cls_id = int(parts[0])
            x_center, y_center, width, height = [float(value) for value in parts[1:]]
        except ValueError:
            continue
        boxes.append((cls_id, x_center, y_center, width, height, line_no))
    return boxes


def collect_bbox_size_outlier_issues(
    ctx: CheckContext,
    tiny_area: float = DEFAULT_TINY_AREA,
    huge_area: float = DEFAULT_HUGE_AREA,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    snap = ctx.snapshot
    for split, images in snap.images_per_split.items():
        labels = snap.labels_per_split.get(split, ())
        label_by_stem = {label.stem: label for label in labels}
        for image_path in images:
            label_path = label_by_stem.get(image_path.stem, _label_for_image(image_path))
            for cls_id, _x, _y, width, height, line_no in _parse_yolo_boxes(label_path):
                area = width * height
                if 0 < area < tiny_area:
                    issues.append({
                        "split": split,
                        "image": str(image_path),
                        "label": str(label_path),
                        "line_no": line_no,
                        "kind": "tiny_bbox",
                        "detail": f"第 {line_no} 行目标框面积过小: {area:.8f}",
                        "repair_suggestion": "放大查看目标是否真实存在；误标点框应删除或重标。",
                        "class_id": cls_id,
                        "width": width,
                        "height": height,
                        "area": area,
                        "threshold": tiny_area,
                    })
                elif area > huge_area:
                    issues.append({
                        "split": split,
                        "image": str(image_path),
                        "label": str(label_path),
                        "line_no": line_no,
                        "kind": "huge_bbox",
                        "detail": f"第 {line_no} 行目标框覆盖面积过大: {area:.4f}",
                        "repair_suggestion": "核验是否把整图误标为目标；必要时重新收紧边界框。",
                        "class_id": cls_id,
                        "width": width,
                        "height": height,
                        "area": area,
                        "threshold": huge_area,
                    })

    details = {
        "tiny_area": tiny_area,
        "huge_area": huge_area,
        "issues_preview": issues[:DETAILS_PREVIEW_LIMIT],
    }
    return issues, details


@check("bbox_size_outliers")
def validate_bbox_size_outliers(ctx: CheckContext) -> CheckResult:
    issues, details = collect_bbox_size_outlier_issues(ctx)
    if not issues:
        return CheckResult(
            name="bbox_size_outliers",
            severity=CheckSeverity.PASS,
            summary="未发现极端面积目标框",
            details=details,
        )
    return CheckResult(
        name="bbox_size_outliers",
        severity=CheckSeverity.WARNING,
        summary=f"发现 {len(issues)} 个极端面积目标框",
        details=details,
    )
