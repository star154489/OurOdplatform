"""扩展点4：生成 HTML 和 Word 格式质检报告。"""
from __future__ import annotations

import argparse
import html
from collections import Counter
from pathlib import Path
from typing import Any, Optional, Sequence

from od_platform.data_validation.extended_common import ExtendedCheckResult, ExtendedIssue
from od_platform.data_validation.extended_records import collect_base_report_issues
from od_platform.data_validation.registry import CheckSeverity, ValidationOptions
from od_platform.data_validation.service import validate_dataset


def write_html_report(path: Path, report: Any, checks: Sequence[ExtendedCheckResult], issues: Sequence[ExtendedIssue]) -> None:
    severity_counts = Counter(issue.severity for issue in issues)
    rows = []
    for issue in issues[:500]:
        rows.append(
            "<tr>"
            f"<td>{html.escape(issue.severity)}</td>"
            f"<td>{html.escape(issue.check_name)}</td>"
            f"<td>{html.escape(issue.split)}</td>"
            f"<td>{html.escape(issue.issue_type)}</td>"
            f"<td>{html.escape(issue.image_path)}</td>"
            f"<td>{html.escape(issue.message)}</td>"
            f"<td>{html.escape(issue.repair_suggestion)}</td>"
            "</tr>"
        )
    check_cards = "".join(
        f"<li><strong>{html.escape(check.name)}</strong> [{html.escape(check.severity)}] "
        f"{html.escape(check.summary)}</li>" for check in checks
    ) or "<li>未传入额外扩展检测结果，仅展示原生质检问题明细。</li>"
    content = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>ODPlatform 扩展数据质检报告</title>
<style>
body {{ font-family: 'Microsoft YaHei', Arial, sans-serif; margin: 32px; color: #1f2937; }}
.summary {{ display: flex; gap: 16px; flex-wrap: wrap; }}
.card {{ border: 1px solid #e5e7eb; border-radius: 10px; padding: 16px; min-width: 150px; background: #f9fafb; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 16px; font-size: 13px; }}
th, td {{ border: 1px solid #e5e7eb; padding: 8px; vertical-align: top; }}
th {{ background: #eef2ff; }}
</style>
</head>
<body>
<h1>ODPlatform 扩展数据质检报告</h1>
<p><strong>Run ID:</strong> {html.escape(report.run_id)} | <strong>数据集:</strong> {html.escape(str(report.yaml_path))}</p>
<div class="summary">
<div class="card"><h3>总体等级</h3><p>{html.escape(report.overall_severity)}</p></div>
<div class="card"><h3>问题总数</h3><p>{len(issues)}</p></div>
<div class="card"><h3>ERROR</h3><p>{severity_counts.get(CheckSeverity.ERROR, 0)}</p></div>
<div class="card"><h3>WARNING</h3><p>{severity_counts.get(CheckSeverity.WARNING, 0)}</p></div>
</div>
<h2>扩展检测项</h2>
<ul>{check_cards}</ul>
<h2>问题明细（最多展示 500 条，完整内容见 CSV）</h2>
<table>
<thead><tr><th>等级</th><th>检测项</th><th>划分</th><th>类型</th><th>图像</th><th>问题</th><th>修复建议</th></tr></thead>
<tbody>{''.join(rows)}</tbody>
</table>
</body>
</html>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_word_report(path: Path, report: Any, checks: Sequence[ExtendedCheckResult], issues: Sequence[ExtendedIssue]) -> None:
    """写出 Word 可直接打开的 HTML 兼容 .doc 文件，无需额外依赖。"""
    temp_html = path.with_suffix(".word.html")
    write_html_report(temp_html, report, checks, issues)
    body = temp_html.read_text(encoding="utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    try:
        temp_html.unlink()
    except OSError:
        pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="扩展点4：生成 HTML 和 Word 质检报告")
    parser.add_argument("--data", "--yaml", dest="yaml_path", required=True, type=Path, help="数据集 yaml 路径")
    parser.add_argument("--task", dest="task_type", default=None, help="任务类型: detect/segment，默认读取 yaml")
    parser.add_argument("--run-dir", default=None, type=Path, help="指定报告输出目录")
    parser.add_argument("--html-out", type=Path, default=None, help="HTML 输出路径，默认写入 run_dir/report.html")
    parser.add_argument("--word-out", type=Path, default=None, help="Word 输出路径，默认写入 run_dir/report.doc")
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
    output_dir = report.run_dir or Path.cwd()
    issues = collect_base_report_issues(report)
    html_path = args.html_out or (output_dir / "report.html")
    word_path = args.word_out or (output_dir / "report.doc")
    write_html_report(html_path, report, [], issues)
    write_word_report(word_path, report, [], issues)
    print(f"HTML报告已写入: {html_path}")
    print(f"Word报告已写入: {word_path}")
    return 2 if any(issue.severity == CheckSeverity.ERROR for issue in issues) else 0


if __name__ == "__main__":
    raise SystemExit(main())
