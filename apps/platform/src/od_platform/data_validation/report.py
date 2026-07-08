#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  : report.py
# @Function  : ValidationReport — 一次验证的完整产出 (纯数据)
"""ValidationReport — 一次验证的完整产出 (纯数据)。

设计原则: 只装数据 + 派生属性 + to_dict。
所有"怎么展示给人看"的逻辑归 render 层 — 这是 D4 撞墙③ 的解药。

派生属性 (永不存值):
    - overall_severity:   全部结果里最严重的级别
    - counts_by_severity: 各级别计数
    - exit_code:          0/1/2 — Unix 退出码语义
    - failed_results:     非 PASS 的 results 子集
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from od_platform.data_validation.registry import CheckResult, CheckSeverity
from od_platform.data_validation.snapshot import DatasetSnapshot


@dataclass
class ValidationReport:
    """一次验证的完整产出。

    schema 承诺: 新字段只增不改 — 老消费者读 report.json 不受影响 (additive)。
    """
    run_id:           str
    yaml_path:        Path
    snapshot:         DatasetSnapshot
    results:          List[CheckResult]
    duration_seconds: float
    started_at_iso:   str
    run_dir:          Optional[Path] = None
    fingerprint:      Optional[Dict[str, Any]] = None
    profile:          Optional[Dict[str, Any]] = None
    operator:         Optional[str] = None
    tool_version:     Optional[str] = None
    environment:      Optional[Dict[str, str]] = None

    # ── 派生属性 (从 results 算, 不存值) ──

    @property
    def overall_severity(self) -> str:
        if not self.results:
            return CheckSeverity.PASS
        return max(self.results, key=lambda r: CheckSeverity.rank(r.severity)).severity

    @property
    def counts_by_severity(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for r in self.results:
            counts[r.severity] = counts.get(r.severity, 0) + 1
        return counts

    @property
    def exit_code(self) -> int:
        sev = self.overall_severity
        if sev == CheckSeverity.ERROR:
            return 2
        if sev == CheckSeverity.WARNING:
            return 1
        return 0

    @property
    def failed_results(self) -> List[CheckResult]:
        return [r for r in self.results if not r.passed]

    @property
    def report_path(self) -> Optional[Path]:
        return (self.run_dir / "report.json") if self.run_dir else None

    # ── JSON 序列化 ──

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id":           self.run_id,
            "yaml_path":        str(self.yaml_path),
            "task_type":        self.snapshot.task_type,
            "started_at":       self.started_at_iso,
            "duration_seconds": round(self.duration_seconds, 3),
            "overall_severity": self.overall_severity,
            "exit_code":        self.exit_code,
            "counts":           self.counts_by_severity,
            "tool_version":     self.tool_version,
            "operator":         self.operator,
            "environment":      self.environment,
            "dataset_summary": {
                "nc":          self.snapshot.nc,
                "class_names": list(self.snapshot.class_names),
                "stats_per_split": {
                    split: {
                        "image_count":     stat.image_count,
                        "annotated_count": stat.annotated_count,
                        "total_instances": stat.total_instances,
                    }
                    for split, stat in self.snapshot.stats_per_split.items()
                },
            },
            "fingerprint": self.fingerprint,
            "results": [
                {
                    "name":     r.name,
                    "severity": r.severity,
                    "summary":  r.summary,
                    "details":  r.details,
                }
                for r in self.results
            ],
        }
