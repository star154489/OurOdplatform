"""odp-validate CLI — D4 子系统的端到端入口。

用法:
    odp-validate --dataset NAME [--task detect|segment] [--operator NAME]
    odp-validate --yaml /path/to/yaml [--check-images] [--no-profile]

退出码:
    0  PASS or only INFO
    1  WARNING present
    2  ERROR present
    3  Ctrl-C or unexpected exception (CLI bug, not data issue)
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from od_platform.common.constants import Task
from od_platform.common.logging_utils import get_logger
from od_platform.common.paths import LOGGING_DIR, DATASET_CONFIGS_DIR
from od_platform.data_validation.extended_validation import write_extended_validation_artifacts
from od_platform.data_validation.registry import ValidationOptions
from od_platform.data_validation.render import render_to_logger
from od_platform.data_validation.service import validate_dataset


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="odp-validate",
        description="YOLO 数据集质量验证 (data_validation 子系统的 CLI 入口)",
    )

    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--dataset",
        help="数据集名 (= configs/datasets/<name>.yaml 的 stem; 日常使用)",
    )
    source.add_argument(
        "--yaml",
        type=Path,
        help="直接指定 yaml 完整路径 (调试 / 临时数据集用)",
    )

    parser.add_argument(
        "--task",
        choices=Task.all(),
        default=None,
        help="任务类型 (None = 读 yaml.task 字段, 仍读不到则 detect)",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="不写报告产物 (只跑验证, 看日志即可)",
    )
    parser.add_argument(
        "--check-images",
        action="store_true",
        help="开启图像完整性深度检查 (逐张解码, 重型; 接入第三方数据时建议开)",
    )
    parser.add_argument(
        "--no-profile",
        action="store_true",
        help="跳过实例画像与 instances.csv 生成 (超大数据集快速过闸用)",
    )
    parser.add_argument(
        "--report-format",
        choices=("md", "html", "word", "all"),
        default="md",
        help="质检报告格式: md/html/word/all，默认 md",
    )
    parser.add_argument(
        "--enable-phash",
        action="store_true",
        help="启用重型 Phash 近重复图像检测",
    )
    parser.add_argument(
        "--phash-threshold",
        type=int,
        default=5,
        help="Phash 汉明距离阈值，越小越严格",
    )
    parser.add_argument(
        "--phash-max-images",
        type=int,
        default=None,
        help="限制 Phash 最大扫描图像数，便于大数据集抽检",
    )
    parser.add_argument(
        "--no-csv",
        action="store_true",
        help="不生成问题数据 CSV 明细",
    )
    parser.add_argument(
        "--no-image-headers",
        action="store_true",
        help="画像层不读图像头 (放弃分辨率/像素口径字段, 进一步省 I/O)",
    )
    parser.add_argument(
        "--operator",
        default=None,
        help="操作人 (审计字段; 默认取系统用户名)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="DEBUG 级日志输出 (控制台和文件同步开 DEBUG)",
    )

    return parser


def _resolve_yaml(ref: str) -> Path:
    """解析 yaml 路径: 绝对路径原样, 否则去 configs/datasets/ 找。"""
    p = Path(ref)
    if p.is_absolute() or (p.suffix and p.exists()):
        return p.resolve()
    candidate = DATASET_CONFIGS_DIR / f"{ref}.yaml"
    if candidate.exists():
        return candidate.resolve()
    return p.resolve()


def _resolve_report_formats(report_format: str) -> tuple[str, ...]:
    if report_format == "all":
        return ("md", "html", "word")
    return (report_format,)


def main(argv: list | None = None) -> int:
    """CLI 入口。

    Args:
        argv: 命令行参数列表, 默认读取 sys.argv

    Returns:
        int: 退出码 (0/1/2/3)
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logger = get_logger(
        base_path=LOGGING_DIR,
        log_type="validate",
        log_level=log_level,
        logger_name="od_platform.cli.validate_data",
    )

    try:
        ref = args.dataset if args.dataset else str(args.yaml)
        yaml_path = _resolve_yaml(ref)
        logger.info(f"验证数据集 YAML: {yaml_path}")

        options = ValidationOptions(
            check_images=args.check_images,
            profile=not args.no_profile,
            read_image_headers=not args.no_image_headers,
        )

        report = validate_dataset(
            yaml_path=yaml_path,
            task_type=args.task,
            write_report=not args.no_report,
            options=options,
            operator=args.operator,
        )

        render_to_logger(report, logger, report_path=report.report_path)

        if report.markdown_path and report.markdown_path.exists():
            logger.info(f"  Markdown 报告:  {report.markdown_path}")

        if not args.no_report and report.run_dir is not None:
            artifacts = write_extended_validation_artifacts(
                report,
                enable_phash=args.enable_phash,
                phash_threshold=args.phash_threshold,
                phash_max_images=args.phash_max_images,
                report_formats=_resolve_report_formats(args.report_format),
                write_csv=not args.no_csv,
            )
            if not args.no_csv:
                logger.info(f"  问题CSV明细: {artifacts.issues_csv}")
            logger.info(f"  扩展质检摘要: {artifacts.extended_json}")
            if artifacts.html_report:
                logger.info(f"  HTML 报告:    {artifacts.html_report}")
            if artifacts.word_report:
                logger.info(f"  Word 报告:    {artifacts.word_report}")

            has_extended_error = any(check.severity == "ERROR" for check in artifacts.checks)
            if has_extended_error and report.exit_code < 2:
                return 2
            if artifacts.issue_count > 0 and report.exit_code == 0:
                return 1

        return report.exit_code

    except KeyboardInterrupt:
        logger.warning("用户中断 (Ctrl-C)")
        return 3
    except Exception:
        logger.exception("未预期异常 — CLI bug, 不是数据问题")
        return 3


if __name__ == "__main__":
    sys.exit(main())
