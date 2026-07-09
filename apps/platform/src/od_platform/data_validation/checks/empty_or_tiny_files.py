"""empty_or_tiny_files check — 空文件、异常小文件检测。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from od_platform.data_validation.registry import check, CheckContext, CheckResult, CheckSeverity

DETAILS_PREVIEW_LIMIT = 50
DEFAULT_MIN_IMAGE_BYTES = 512


def _label_for_image(image_path: Path) -> Path:
    parts = list(image_path.parts)
    for index in range(len(parts) - 1, -1, -1):
        if parts[index] == "images":
            parts[index] = "labels"
            break
    return Path(*parts[:-1]) / f"{image_path.stem}.txt"


def _iter_image_label_pairs(ctx: CheckContext):
    snap = ctx.snapshot
    for split, images in snap.images_per_split.items():
        labels = snap.labels_per_split.get(split, ())
        label_by_stem = {label.stem: label for label in labels}
        for image_path in images:
            yield split, image_path, label_by_stem.get(image_path.stem, _label_for_image(image_path))


def collect_empty_or_tiny_file_issues(
    ctx: CheckContext,
    min_image_bytes: int = DEFAULT_MIN_IMAGE_BYTES,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    counts = {"empty_image": 0, "tiny_image_file": 0, "empty_label": 0}

    for split, image_path, label_path in _iter_image_label_pairs(ctx):
        try:
            image_size = image_path.stat().st_size
        except OSError:
            image_size = -1
        if image_size <= 0:
            counts["empty_image"] += 1
            issues.append({
                "split": split,
                "image": str(image_path),
                "label": str(label_path),
                "kind": "empty_image",
                "detail": "图像文件为空或无法读取大小",
                "repair_suggestion": "从原始数据重新拷贝该图像，或从数据集中移除对应图像和标签。",
                "size_bytes": image_size,
            })
        elif image_size < min_image_bytes:
            counts["tiny_image_file"] += 1
            issues.append({
                "split": split,
                "image": str(image_path),
                "label": str(label_path),
                "kind": "tiny_image_file",
                "detail": f"图像文件体积过小: {image_size} bytes",
                "repair_suggestion": "人工打开核验是否为损坏缩略图；若损坏请替换或删除。",
                "size_bytes": image_size,
                "threshold": min_image_bytes,
            })
        if label_path.exists():
            try:
                label_size = label_path.stat().st_size
            except OSError:
                label_size = -1
            if label_size == 0:
                counts["empty_label"] += 1
                issues.append({
                    "split": split,
                    "image": str(image_path),
                    "label": str(label_path),
                    "kind": "empty_label",
                    "detail": "标签文件为空",
                    "repair_suggestion": "确认该图是否允许无目标；若不允许，请补标或移入负样本策略。",
                    "size_bytes": label_size,
                })

    details = {
        "min_image_bytes": min_image_bytes,
        "issue_counts": counts,
        "issues_preview": issues[:DETAILS_PREVIEW_LIMIT],
    }
    return issues, details


@check("empty_or_tiny_files")
def validate_empty_or_tiny_files(ctx: CheckContext) -> CheckResult:
    issues, details = collect_empty_or_tiny_file_issues(ctx)
    if not issues:
        return CheckResult(
            name="empty_or_tiny_files",
            severity=CheckSeverity.PASS,
            summary="未发现空文件/异常小文件",
            details=details,
        )
    has_empty_image = details["issue_counts"].get("empty_image", 0) > 0
    return CheckResult(
        name="empty_or_tiny_files",
        severity=CheckSeverity.ERROR if has_empty_image else CheckSeverity.WARNING,
        summary=f"发现 {len(issues)} 个空文件或异常小文件问题",
        details=details,
    )
