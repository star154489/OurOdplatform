"""扩展点3：输出详细问题 CSV，并为问题样本提供修复建议。"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any, List, Optional, Sequence

from od_platform.data_validation.extended_common import ExtendedIssue
from od_platform.data_validation.registry import CheckSeverity, ValidationOptions
from od_platform.data_validation.service import validate_dataset


def base_repair_suggestion(check_name: str) -> str:
    suggestions = {
        "label_format": "按 YOLO 格式修复标签行：detect 为 class x_center y_center width height，坐标归一化到 [0,1]。",
        "pair_existence": "补齐缺失的图像/标签文件，或删除无法配对的孤立文件。",
        "bbox_within_image": "重新计算并裁剪越界框，必要时回到标注工具修正。",
        "duplicate_annotations": "删除同一图像内重复标注框，仅保留一条准确标注。",
        "orphan_labels": "删除无对应图像的标签文件，或补回缺失图像。",
        "split_uniqueness": "重新划分数据集，确保同一图像不跨 train/val/test。",
        "box_geometry": "重新检查退化框、极端宽高比框，必要时回标注工具重标。",
        "class_balance": "结合业务目标补充少数类样本，或在训练阶段采用重采样/增强策略。",
        "annotation_coverage": "确认无标注图是否为负样本；误漏标样本应补标。",
        "empty_or_tiny_files": "回源替换损坏/异常小图像；空标签需确认是否为负样本或补标。",
        "label_density_outliers": "核验目标数量离群图像，重点检查漏标、重复框和密集误标。",
        "bbox_size_outliers": "核验极小/极大目标框，误标框应删除或重新标注。",
        "image_resolution_outliers": "回源检查低分辨率、极端宽高比或无法打开的图像。",
    }
    return suggestions.get(check_name, "查看原始检查项详情，按数据集规范修复后重新运行质检。")


def collect_base_report_issues(report: Any) -> List[ExtendedIssue]:
    """把原生 CheckResult 中的 preview 类问题转换为统一 CSV 记录。"""
    issues: List[ExtendedIssue] = []
    for result in report.results:
        if result.severity == CheckSeverity.PASS:
            continue
        details = result.details or {}
        for key in ("errors_preview", "issues_preview", "duplicates_preview", "orphan_preview", "examples"):
            previews = details.get(key)
            if not isinstance(previews, list):
                continue
            for item in previews:
                if not isinstance(item, dict):
                    continue
                label = item.get("label") or item.get("label_path") or ""
                image = item.get("image") or item.get("image_path") or ""
                issues.append(ExtendedIssue(
                    check_name=result.name,
                    severity=result.severity,
                    split=str(item.get("split", "")),
                    image_path=str(image),
                    label_path=str(label),
                    issue_type=str(item.get("kind") or item.get("issue_type") or key),
                    message=str(item.get("detail") or item.get("message") or result.summary),
                    repair_suggestion=str(item.get("repair_suggestion") or base_repair_suggestion(result.name)),
                    extra=item,
                ))
    return issues


def write_issues_csv(path: Path, issues: Sequence[ExtendedIssue]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "check_name", "severity", "split", "image_path", "label_path",
        "issue_type", "message", "repair_suggestion", "extra_json",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=fieldnames)
        writer.writeheader()
        for issue in issues:
            writer.writerow(issue.to_csv_row())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="扩展点3：生成详细问题 CSV 和修复建议")
    parser.add_argument("--data", "--yaml", dest="yaml_path", required=True, type=Path, help="数据集 yaml 路径")
    parser.add_argument("--task", dest="task_type", default=None, help="任务类型: detect/segment，默认读取 yaml")
    parser.add_argument("--run-dir", default=None, type=Path, help="指定原生质检报告输出目录")
    parser.add_argument("--out", type=Path, default=None, help="CSV 输出路径，默认写入 run_dir/issues_detailed.csv")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    report = validate_dataset(
        yaml_path=args.yaml_path,
        task_type=args.task_type,
        run_dir=args.run_dir,
        write_report=True,
        options=ValidationOptions(check_images=True, profile=True),
    )
    issues = collect_base_report_issues(report)
    out_path = args.out or ((report.run_dir or Path.cwd()) / "issues_detailed.csv")
    write_issues_csv(out_path, issues)
    print(f"CSV明细已写入: {out_path}")
    return 2 if any(issue.severity == CheckSeverity.ERROR for issue in issues) else 0


if __name__ == "__main__":
    raise SystemExit(main())
