"""render_markdown — 14 章节企业报告 (Markdown)。

数据/展示分离的第二笔分红: 加新展示 = 加新 renderer, 报告数据结构零改动。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from od_platform.common.constants import RENDER_INDENT
from od_platform.data_validation.registry import CheckResult, CheckSeverity
from od_platform.data_validation.report import ValidationReport

logger = logging.getLogger(__name__)

_GRADE_MAP = {
    CheckSeverity.PASS:    ("A", "放行", "全部检查通过, 可直接进入训练流程。"),
    CheckSeverity.INFO:    ("B", "放行 (附关注项)", "存在提示级发现, 不阻断训练, 建议训练前过目。"),
    CheckSeverity.WARNING: ("C", "有条件放行", "存在警告级问题, 需数据负责人确认风险后方可放行。"),
    CheckSeverity.ERROR:   ("D", "阻断", "存在错误级问题, 必须整改并重新验证后才能进入训练。"),
}

_ACTION_HINTS = {
    "yaml_schema":           "修正 yaml 配置字段后重跑验证",
    "pair_existence":        "补齐缺失标签或移除对应图像",
    "label_format":          "用 instances.csv 定位坏行, 修正后重新导出",
    "split_uniqueness":      "从重叠划分中移除重复样本, 重新切分",
    "box_geometry":          "按 instances.csv 的 degenerate 标记清理退化框",
    "annotation_coverage":   "确认无标注图是否为有意背景图, 否则补标或剔除",
    "bbox_within_image":     "检查标注工具坐标系/增强导出, 修正出图框",
    "orphan_labels":         "清理无对应图像的标签文件, 排查数据同步脚本",
    "stem_collision":        "人工裁决同名图像保留哪张, 统一扩展名规范",
    "split_presence":        "核对 yaml 声明与磁盘目录, 补齐缺失划分",
    "class_presence":        "为缺失类别补充训练样本, 或从类别表移除死类别",
    "class_balance":         "评估重采样 / class_weights / 定向采集少数类",
    "duplicate_annotations": "按 instances.csv 的 exact_duplicate 标记去重",
    "image_integrity":       "替换或剔除损坏图像; EXIF 旋转图建议落盘前归一化",
}


def _table(headers: List[str], rows: List[List[Any]]) -> str:
    """Markdown 表格。空 rows 返回占位行。"""
    out = ["| " + " | ".join(str(h) for h in headers) + " |",
           "|" + "|".join([" --- "] * len(headers)) + "|"]
    if not rows:
        out.append("| " + " | ".join(["—"] * len(headers)) + " |")
    for row in rows:
        out.append("| " + " | ".join(
            "—" if v is None or v == "" else str(v) for v in row
        ) + " |")
    return "\n".join(out)


def _bar(count: int, max_count: int, width: int = 20) -> str:
    if max_count <= 0:
        return ""
    n = round(count / max_count * width)
    return "█" * max(n, 1 if count > 0 else 0)


def _load_previous_summary(report: ValidationReport) -> Optional[Dict[str, Any]]:
    """在 run_dir 的同级目录里找最近一次 report.json (趋势对比)。"""
    try:
        if report.run_dir is None:
            return None
        runs_root = report.run_dir.parent
        candidates = []
        for d in runs_root.iterdir():
            if not d.is_dir() or d.name >= report.run_id:
                continue
            rp = d / "report.json"
            if rp.exists():
                candidates.append((d.name, rp))
        if not candidates:
            return None
        _, prev_path = max(candidates)
        return json.loads(prev_path.read_text(encoding="utf-8"))
    except Exception:
        logger.debug("读取历史报告失败, 趋势段降级", exc_info=True)
        return None


def render_markdown(report: ValidationReport) -> str:
    """生成 14 章节企业报告 Markdown 字符串。"""
    grade, grade_label, grade_desc = _GRADE_MAP.get(
        report.overall_severity, ("?", "未知", "")
    )
    lines: List[str] = []

    # ==== 第 1 节: 报告元数据 ====
    lines.append("# YOLO 数据集验证报告\n")
    lines.append("## 1. 报告元数据\n")
    lines.append(f"- **运行 ID**: `{report.run_id}`")
    lines.append(f"- **数据集 YAML**: `{report.yaml_path}`")
    lines.append(f"- **任务类型**: `{report.snapshot.task_type}`")
    lines.append(f"- **工具版本**: `{report.tool_version or '未知'}`")
    lines.append(f"- **操作人**: `{report.operator or '未指定'}`")
    lines.append(f"- **运行时间**: `{report.started_at_iso}`")
    lines.append(f"- **总耗时**: `{report.duration_seconds:.2f}s`")
    lines.append("")
    if report.environment:
        env = report.environment
        lines.append("| 环境属性 | 值 |")
        lines.append("| --- | --- |")
        for k, v in env.items():
            lines.append(f"| {k} | {v} |")
        lines.append("")
    if report.fingerprint:
        fp = report.fingerprint
        lines.append(f"- **数据指纹 (SHA256)**: `{fp.get('manifest_sha256', 'N/A')}`")
        lines.append(f"- **指纹算法**: {fp.get('algorithm', 'N/A')}")
        lines.append(f"- **覆盖文件**: {fp.get('total_files', 'N/A')} 个, {fp.get('total_bytes', 'N/A')} 字节")
        lines.append("")

    # ==== 第 2 节: 执行摘要 ====
    lines.append("## 2. 执行摘要\n")
    lines.append(f"| 维度 | 结果 |")
    lines.append(f"| --- | --- |")
    lines.append(f"| **总体评级** | **{grade} — {grade_label}** |")
    lines.append(f"| **详细说明** | {grade_desc} |")
    lines.append("")
    counts = report.counts_by_severity
    lines.append(_table(
        ["级别", "数量"],
        [[s, counts.get(s, 0)] for s in (CheckSeverity.ERROR, CheckSeverity.WARNING, CheckSeverity.INFO, CheckSeverity.PASS)]
    ))
    lines.append(f"\n**退出码**: `{report.exit_code}` (0=放行, 1=有条件放行, 2=阻断, 3=工具异常)\n")

    # ==== 第 3 节: 检查结果总表 ====
    lines.append("## 3. 检查结果总表\n")
    lines.append(_table(
        ["#", "检查项", "结果", "摘要"],
        [[i + 1, r.name, r.severity, r.summary] for i, r in enumerate(report.results)]
    ))
    lines.append("")

    # ==== 第 4-9 节: 数据集信息 + 画像 ====
    snap = report.snapshot
    lines.append("## 4. 数据集基本信息\n")
    lines.append(f"- **类别数 (nc)**: {snap.nc}")
    if snap.class_names:
        lines.append(f"- **类别列表**: {', '.join(snap.class_names)}")
    lines.append("")
    for split, stat in snap.stats_per_split.items():
        lines.append(f"### {split}\n")
        lines.append(_table(
            ["指标", "值"],
            [["图像数", stat.image_count],
             ["有标注图", stat.annotated_count],
             ["实例总数", stat.total_instances]]
        ))
        lines.append("")

    # 第 5 节: 类别分布
    lines.append("## 5. 类别分布\n")
    for split in snap.splits:
        st = snap.stats_per_split.get(split)
        if not st or not st.class_instances:
            continue
        max_count = max(st.class_instances.values()) if st.class_instances else 1
        rows = []
        for cid in range(snap.nc or 0):
            name = snap.class_names[cid] if cid < len(snap.class_names) else f"id_{cid}"
            count = st.class_instances.get(cid, 0)
            rows.append([name, count, _bar(count, max_count)])
        lines.append(f"### {split}\n")
        lines.append(_table(["类别", "实例数", "分布"], rows))
        lines.append("")

    # 第 6 节: 划分一致性
    lines.append("## 6. 划分一致性\n")
    if report.profile and report.profile.get("consistency"):
        for key, val in report.profile["consistency"].items():
            lines.append(f"- **{key}**: JSD={val['jsd']}, 等级={val['level']}")
    else:
        lines.append("(画像未开启或无足够数据计算)\n")
    lines.append("")

    # 第 7 节: bbox 几何
    lines.append("## 7. bbox 几何\n")
    if report.profile and report.profile.get("per_split_class"):
        for split, classes in report.profile["per_split_class"].items():
            rows = []
            for cname, stats in classes.items():
                rows.append([
                    cname, stats["count"], stats["area_mean"],
                    stats["ar_mean"], stats["small_norm"],
                    stats["touches_border"], stats["degenerate"],
                ])
            lines.append(f"### {split}\n")
            lines.append(_table(
                ["类别", "实例数", "面积均值", "宽高比均值", "小目标", "贴边", "退化"],
                rows,
            ))
            lines.append("")
    else:
        lines.append("(画像未开启)\n")

    # 第 8 节: 密度/共现/空间
    lines.append("## 8. 密度 / 共现 / 空间分布\n")
    if report.profile:
        prof = report.profile
        lines.append("### 每图实例密度\n")
        density = prof.get("density", {})
        if density:
            max_d = max(density.values()) if density else 1
            lines.append(_table(
                ["区间", "图数", "分布"],
                [[k, v, _bar(v, max_d)] for k, v in sorted(density.items(), key=lambda x: float(x[0].split("-")[0].split("+")[0]))]
            ))
            lines.append("")
        lines.append("### 类别共现 (Top 20)\n")
        cooc = prof.get("co_occurrence", [])
        if cooc:
            lines.append(_table(
                ["类别对", "共现次数"],
                [[f"{c['classes'][0]} ↔ {c['classes'][1]}", c["count"]] for c in cooc]
            ))
            lines.append("")
    else:
        lines.append("(画像未开启)\n")

    # 第 9 节: 图像级画像
    lines.append("## 9. 图像级画像\n")
    img_integrity = None
    for r in report.results:
        if r.name == "image_integrity":
            img_integrity = r
            break
    if img_integrity and img_integrity.details.get("mode_distribution"):
        det = img_integrity.details
        lines.append("### 通道模式分布\n")
        lines.append(_table(
            ["模式", "图像数"],
            list(det.get("mode_distribution", {}).items())
        ))
        lines.append("\n### 分辨率 Top 10\n")
        lines.append(_table(
            ["分辨率", "图像数"],
            [[r["size"], r["count"]] for r in det.get("resolution_top", [])]
        ))
        lines.append(f"\n- 最小分辨率: {det.get('resolution_min', 'N/A')}")
        lines.append(f"\n- 最大分辨率: {det.get('resolution_max', 'N/A')}\n")
    else:
        lines.append("(图像完整性检查未开启, 无图像级数据)\n")

    # ==== 第 10 节: 异常锚点 ====
    lines.append("## 10. 异常锚点 Top-N\n")
    if report.profile:
        anchors = report.profile.get("anomaly_anchors", {})
        small = anchors.get("smallest_areas", [])
        if small:
            lines.append("### 最小面积框\n")
            lines.append(_table(
                ["图像", "行号", "归一化面积"],
                [[s["image"], s["line"], s["area"]] for s in small]
            ))
            lines.append("")
        extreme = anchors.get("extreme_aspect_ratios", [])
        if extreme:
            lines.append("### 极端宽高比框\n")
            lines.append(_table(
                ["图像", "行号", "宽高比"],
                [[e["image"], e["line"], e["ar"]] for e in extreme]
            ))
            lines.append("")
    else:
        lines.append("(画像未开启)\n")

    # ==== 第 11 节: 问题清单 + 建议 ====
    lines.append("## 11. 问题清单与建议动作\n")
    failed = report.failed_results
    if failed:
        rows = []
        for r in failed:
            hint = _ACTION_HINTS.get(r.name, "检查数据来源并修正")
            rows.append([r.name, r.severity, hint])
        lines.append(_table(["检查项", "级别", "建议动作"], rows))
    else:
        lines.append("无待处理问题。\n")
    lines.append("")

    # ==== 第 12 节: 趋势对比 ====
    lines.append("## 12. 与上次运行对比\n")
    prev = _load_previous_summary(report)
    if prev:
        prev_sev = prev.get("overall_severity", "?")
        lines.append(f"上一次运行: `{prev.get('run_id', '?')}` ({prev.get('started_at', '?')})\n")
        prev_counts = prev.get("counts", {})
        cur_counts = report.counts_by_severity
        lines.append(_table(
            ["指标", "本次 (变化)"],
            [
                [f"总体评级", f"{prev_sev} → {report.overall_severity}", "—"],
                ["ERROR 数", f"{cur_counts.get(CheckSeverity.ERROR, 0)} ({cur_counts.get(CheckSeverity.ERROR, 0) - prev_counts.get(CheckSeverity.ERROR, 0):+d})", "—"],
                ["WARNING 数", f"{cur_counts.get(CheckSeverity.WARNING, 0)} ({cur_counts.get(CheckSeverity.WARNING, 0) - prev_counts.get(CheckSeverity.WARNING, 0):+d})", "—"],
            ]
        ))
    else:
        lines.append("首次运行, 无历史数据可比对。\n")
    lines.append("")

    # ==== 第 13 节: 签字栏 ====
    lines.append("## 13. 签字栏\n")
    lines.append("| 角色 | 姓名 | 日期 | 签名 |")
    lines.append("| --- | --- | --- | --- |")
    lines.append("| 验证执行人 | | | |")
    lines.append("| 数据负责人 | | | |")
    lines.append("| 放行批准人 | | | |\n")

    # ==== 第 14 节: 合规提示 ====
    lines.append("## 14. 合规提示\n")
    pii_classes = {"person", "face", "head", "pedestrian", "human", "people"}
    if snap.class_names and any(c.lower() in pii_classes for c in snap.class_names):
        lines.append("> ⚠️ **本数据集包含人员影像相关类别**, 请注意:\n")
        lines.append("> 1. 确认数据采集已获得当事人知情同意 (或符合合法处理基础)")
        lines.append("> 2. 确认训练数据不包含《个人信息保护法》定义的敏感个人信息 (如人脸、指纹等)")
        lines.append("> 3. 模型部署后, 建议在最终产品中提供隐私政策的透明说明\n")
    else:
        lines.append("未检测到人员影像相关类别。如实际数据包含人员影像, 请自行完成合规审查。\n")

    lines.append("---\n")
    lines.append("*报告由 ODPlatform data_validation 子系统自动生成。*\n")

    return "\n".join(lines)
