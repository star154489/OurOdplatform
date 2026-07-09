"""数据质量扩展产物统一入口。

新增的轻量检测项已经按原生 checks 风格拆入 data_validation/checks/ 目录，
本文件只负责 Phash 重型检测、CSV 明细和 HTML/Word 报告等扩展产物。
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, List, Optional, Sequence

from od_platform.data_validation.extended_common import (
    ExtendedCheckResult,
    ExtendedIssue,
    ExtendedValidationArtifacts,
)
from od_platform.data_validation.extended_phash import check_phash_duplicates
from od_platform.data_validation.extended_records import collect_base_report_issues, write_issues_csv
from od_platform.data_validation.extended_reports import write_html_report, write_word_report
from od_platform.data_validation.registry import CheckSeverity, ValidationOptions
from od_platform.data_validation.service import validate_dataset

REPORT_FORMATS = ("md", "html", "word")


def write_extended_validation_artifacts(
    report: Any,
    enable_phash: bool = False,
    phash_threshold: int = 5,
    phash_max_images: Optional[int] = None,
    report_formats: Sequence[str] = ("md",),
    write_csv: bool = True,
) -> ExtendedValidationArtifacts:
    """基于原生 ValidationReport 追加扩展检查、CSV 明细和可选格式报告。"""
    output_dir = report.run_dir or Path.cwd()

    checks: List[ExtendedCheckResult] = []
    issues: List[ExtendedIssue] = collect_base_report_issues(report)

    phash_result = None
    if enable_phash:
        phash_result, phash_issues = check_phash_duplicates(
            report.snapshot,
            enabled=True,
            hamming_threshold=phash_threshold,
            max_images=phash_max_images,
        )
        checks.append(phash_result)
        issues.extend(phash_issues)

    selected_formats = {fmt.lower() for fmt in report_formats}
    issues_csv = output_dir / "issues_detailed.csv"
    extended_json = output_dir / "extended_report.json"
    html_report = output_dir / "report.html"
    word_report = output_dir / "report.doc"

    if write_csv:
        write_issues_csv(issues_csv, issues)
    if "html" in selected_formats:
        write_html_report(html_report, report, checks, issues)
    if "word" in selected_formats or "doc" in selected_formats:
        write_word_report(word_report, report, checks, issues)

    extended_payload = {
        "issue_count": len(issues),
        "enabled_extensions": {
            "phash": enable_phash,
            "csv_records": write_csv,
            "report_formats": sorted(selected_formats),
        },
        "checks": [asdict(check) for check in checks],
        "phash": asdict(phash_result) if phash_result is not None else None,
        "issues_csv": str(issues_csv) if write_csv else None,
        "html_report": str(html_report) if "html" in selected_formats else None,
        "word_report": str(word_report) if ("word" in selected_formats or "doc" in selected_formats) else None,
    }
    extended_json.write_text(json.dumps(extended_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    return ExtendedValidationArtifacts(
        run_dir=output_dir,
        issues_csv=issues_csv,
        extended_json=extended_json,
        html_report=html_report if "html" in selected_formats else Path(),
        word_report=word_report if ("word" in selected_formats or "doc" in selected_formats) else Path(),
        issue_count=len(issues),
        checks=checks,
    )


def run_extended_validation(
    yaml_path: Path,
    task_type: Optional[str] = None,
    run_id: Optional[str] = None,
    run_dir: Optional[Path] = None,
    enable_phash: bool = False,
    phash_threshold: int = 5,
    phash_max_images: Optional[int] = None,
    report_formats: Sequence[str] = ("md",),
    write_csv: bool = True,
) -> ExtendedValidationArtifacts:
    """运行原生质检，并按开关调度四个独立扩展脚本。"""
    report = validate_dataset(
        yaml_path=yaml_path,
        task_type=task_type,
        run_id=run_id,
        run_dir=run_dir,
        write_report=True,
        options=ValidationOptions(check_images=True, profile=True),
    )
    return write_extended_validation_artifacts(
        report,
        enable_phash=enable_phash,
        phash_threshold=phash_threshold,
        phash_max_images=phash_max_images,
        report_formats=report_formats,
        write_csv=write_csv,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ODPlatform 数据质量扩展验证统一入口")
    parser.add_argument("--data", "--yaml", dest="yaml_path", required=True, type=Path, help="数据集 yaml 路径")
    parser.add_argument("--task", dest="task_type", default=None, help="任务类型: detect/segment，默认读取 yaml")
    parser.add_argument("--run-id", default=None, help="指定运行 ID")
    parser.add_argument("--run-dir", default=None, type=Path, help="指定报告输出目录")
    parser.add_argument("--report-format", choices=("md", "html", "word", "all"), default="md", help="质检报告格式")
    parser.add_argument("--enable-phash", action="store_true", help="启用扩展点2的重型 Phash 近重复检测")
    parser.add_argument("--phash-threshold", type=int, default=5, help="Phash 汉明距离阈值，越小越严格")
    parser.add_argument("--phash-max-images", type=int, default=None, help="限制 Phash 最大扫描图像数，便于大数据集抽检")
    parser.add_argument("--no-csv", action="store_true", help="不生成扩展点3的 CSV 明细")
    return parser


def _resolve_report_formats(report_format: str) -> Sequence[str]:
    if report_format == "all":
        return REPORT_FORMATS
    return (report_format,)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    artifacts = run_extended_validation(
        yaml_path=args.yaml_path,
        task_type=args.task_type,
        run_id=args.run_id,
        run_dir=args.run_dir,
        enable_phash=args.enable_phash,
        phash_threshold=args.phash_threshold,
        phash_max_images=args.phash_max_images,
        report_formats=_resolve_report_formats(args.report_format),
        write_csv=not args.no_csv,
    )
    print(f"扩展质检完成，问题数: {artifacts.issue_count}")
    print(f"输出目录: {artifacts.run_dir}")
    print(f"扩展摘要: {artifacts.extended_json}")
    print(f"CSV明细: {artifacts.issues_csv}")
    if artifacts.html_report:
        print(f"HTML报告: {artifacts.html_report}")
    if artifacts.word_report:
        print(f"Word报告: {artifacts.word_report}")
    return 2 if any(check.severity == CheckSeverity.ERROR for check in artifacts.checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
