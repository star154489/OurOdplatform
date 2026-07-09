"""label_density_outliers check — 单图目标数离群检测。"""
from __future__ import annotations

import statistics
from pathlib import Path
from typing import Any, Dict, List, Tuple

from od_platform.data_validation.registry import check, CheckContext, CheckResult, CheckSeverity

DETAILS_PREVIEW_LIMIT = 50
DEFAULT_Z_THRESHOLD = 3.0


def _label_for_image(image_path: Path) -> Path:
    parts = list(image_path.parts)
    for index in range(len(parts) - 1, -1, -1):
        if parts[index] == "images":
            parts[index] = "labels"
            break
    return Path(*parts[:-1]) / f"{image_path.stem}.txt"


def _parse_yolo_box_count(label_path: Path) -> int:
    if not label_path.exists():
        return 0
    try:
        lines = label_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0
    count = 0
    for line in lines:
        parts = line.split()
        if len(parts) != 5:
            continue
        try:
            int(parts[0])
            [float(value) for value in parts[1:]]
        except ValueError:
            continue
        count += 1
    return count


def _iter_rows(ctx: CheckContext) -> List[Tuple[str, Path, Path, int]]:
    rows: List[Tuple[str, Path, Path, int]] = []
    snap = ctx.snapshot
    for split, images in snap.images_per_split.items():
        labels = snap.labels_per_split.get(split, ())
        label_by_stem = {label.stem: label for label in labels}
        for image_path in images:
            label_path = label_by_stem.get(image_path.stem, _label_for_image(image_path))
            rows.append((split, image_path, label_path, _parse_yolo_box_count(label_path)))
    return rows


def collect_label_density_outlier_issues(
    ctx: CheckContext,
    z_threshold: float = DEFAULT_Z_THRESHOLD,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    rows = _iter_rows(ctx)
    counts = [count for *_paths, count in rows]
    issues: List[Dict[str, Any]] = []

    if len(counts) < 5:
        return issues, {"message": "样本数少于 5，跳过离群统计", "z_threshold": z_threshold}

    mean_value = statistics.mean(counts)
    stdev_value = statistics.pstdev(counts)
    if stdev_value > 0:
        for split, image_path, label_path, count in rows:
            z_score = (count - mean_value) / stdev_value
            if abs(z_score) >= z_threshold:
                issue_type = "too_many_objects" if z_score > 0 else "too_few_objects"
                suggestion = "检查是否存在重复框、密集误标。" if z_score > 0 else "检查是否漏标；若为背景图，请确认负样本策略。"
                issues.append({
                    "split": split,
                    "image": str(image_path),
                    "label": str(label_path),
                    "kind": issue_type,
                    "detail": f"单图目标数 {count} 明显偏离均值 {mean_value:.2f}",
                    "repair_suggestion": suggestion,
                    "object_count": count,
                    "mean": round(mean_value, 4),
                    "stdev": round(stdev_value, 4),
                    "z_score": round(z_score, 4),
                })

    details = {
        "mean": round(mean_value, 4),
        "stdev": round(stdev_value, 4),
        "z_threshold": z_threshold,
        "issues_preview": issues[:DETAILS_PREVIEW_LIMIT],
    }
    return issues, details


@check("label_density_outliers")
def validate_label_density_outliers(ctx: CheckContext) -> CheckResult:
    issues, details = collect_label_density_outlier_issues(ctx)
    if not issues:
        return CheckResult(
            name="label_density_outliers",
            severity=CheckSeverity.PASS,
            summary="未发现单图目标数离群",
            details=details,
        )
    return CheckResult(
        name="label_density_outliers",
        severity=CheckSeverity.WARNING,
        summary=f"发现 {len(issues)} 张单图目标数离群图像",
        details=details,
    )
