"""路径诊断 CLI 测试。"""
from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "apps" / "platform" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def test_build_paths_report_contains_expected_sections():
    from od_platform.cli.show_paths import build_paths_report

    report = build_paths_report()

    assert "core" in report
    assert "runtime" in report
    assert "reset_targets" in report
    assert "project_core_targets" in report
    assert any(name == "ROOT_DIR" for name, _ in report["core"])
    assert any(value == "runs" for _, value in report["reset_targets"])


def test_show_paths_prints_sections(capsys):
    from od_platform.cli.show_paths import show_paths

    code = show_paths()
    captured = capsys.readouterr()

    assert code == 0
    assert "[CORE]" in captured.out
    assert "[RESET TARGETS]" in captured.out
    assert "[PROJECT CORE TARGETS]" in captured.out
