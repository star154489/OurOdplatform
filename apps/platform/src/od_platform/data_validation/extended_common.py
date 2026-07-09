"""数据质量扩展脚本共享数据结构与工具函数。"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from od_platform.data_validation.registry import CheckSeverity
from od_platform.data_validation.snapshot import DatasetSnapshot


@dataclass
class ExtendedIssue:
    """扩展质检发现的一条可落盘问题记录。"""

    check_name: str
    severity: str
    split: str
    image_path: str
    label_path: str
    issue_type: str
    message: str
    repair_suggestion: str
    extra: Dict[str, Any]

    def to_csv_row(self) -> Dict[str, str]:
        return {
            "check_name": self.check_name,
            "severity": self.severity,
            "split": self.split,
            "image_path": self.image_path,
            "label_path": self.label_path,
            "issue_type": self.issue_type,
            "message": self.message,
            "repair_suggestion": self.repair_suggestion,
            "extra_json": json.dumps(self.extra, ensure_ascii=False),
        }


@dataclass
class ExtendedCheckResult:
    """扩展检测项的聚合结果。"""

    name: str
    severity: str
    summary: str
    issue_count: int
    details: Dict[str, Any]


@dataclass
class ExtendedValidationArtifacts:
    """扩展质检的所有产物路径与统计摘要。"""

    run_dir: Path
    issues_csv: Path
    extended_json: Path
    html_report: Path
    word_report: Path
    issue_count: int
    checks: List[ExtendedCheckResult]


def label_for_image(image_path: Path) -> Path:
    parts = list(image_path.parts)
    for index in range(len(parts) - 1, -1, -1):
        if parts[index] == "images":
            parts[index] = "labels"
            break
    return Path(*parts[:-1]) / f"{image_path.stem}.txt"


def iter_image_label_pairs(snapshot: DatasetSnapshot) -> Iterable[Tuple[str, Path, Path]]:
    for split, images in snapshot.images_per_split.items():
        labels = snapshot.labels_per_split.get(split, ())
        label_by_stem = {label.stem: label for label in labels}
        for image_path in images:
            yield split, image_path, label_by_stem.get(image_path.stem, label_for_image(image_path))


def parse_yolo_boxes(label_path: Path) -> List[Tuple[int, float, float, float, float, int]]:
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


def make_issue(
    check_name: str,
    severity: str,
    split: str,
    image_path: Path,
    label_path: Path,
    issue_type: str,
    message: str,
    repair_suggestion: str,
    **extra: Any,
) -> ExtendedIssue:
    return ExtendedIssue(
        check_name=check_name,
        severity=severity,
        split=split,
        image_path=str(image_path),
        label_path=str(label_path),
        issue_type=issue_type,
        message=message,
        repair_suggestion=repair_suggestion,
        extra=extra,
    )


def severity_from_issues(issues: Sequence[ExtendedIssue]) -> str:
    if any(issue.severity == CheckSeverity.ERROR for issue in issues):
        return CheckSeverity.ERROR
    if any(issue.severity == CheckSeverity.WARNING for issue in issues):
        return CheckSeverity.WARNING
    if any(issue.severity == CheckSeverity.INFO for issue in issues):
        return CheckSeverity.INFO
    return CheckSeverity.PASS
