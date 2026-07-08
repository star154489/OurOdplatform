"""D4 data_validation 核心逻辑测试。"""
from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "apps" / "platform" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


# ---------- CheckSeverity ----------

class TestCheckSeverity:
    def test_rank_order(self):
        from od_platform.data_validation.registry import CheckSeverity
        assert CheckSeverity.rank("PASS") < CheckSeverity.rank("INFO")
        assert CheckSeverity.rank("INFO") < CheckSeverity.rank("WARNING")
        assert CheckSeverity.rank("WARNING") < CheckSeverity.rank("ERROR")

    def test_severity_constants(self):
        from od_platform.data_validation.registry import CheckSeverity
        assert CheckSeverity.PASS == "PASS"
        assert CheckSeverity.INFO == "INFO"
        assert CheckSeverity.WARNING == "WARNING"
        assert CheckSeverity.ERROR == "ERROR"


# ---------- CheckResult ----------

class TestCheckResult:
    def test_passed_property(self):
        from od_platform.data_validation.registry import CheckResult, CheckSeverity
        assert CheckResult(name="t", severity=CheckSeverity.PASS, summary="ok").passed is True
        assert CheckResult(name="t", severity=CheckSeverity.INFO, summary="ok").passed is True
        assert CheckResult(name="t", severity=CheckSeverity.WARNING, summary="w").passed is False
        assert CheckResult(name="t", severity=CheckSeverity.ERROR, summary="e").passed is False

    def test_details_default(self):
        from od_platform.data_validation.registry import CheckResult, CheckSeverity
        r = CheckResult(name="t", severity=CheckSeverity.PASS, summary="ok")
        assert r.details == {}


# ---------- ValidationOptions ----------

class TestValidationOptions:
    def test_defaults(self):
        from od_platform.data_validation.registry import ValidationOptions
        opts = ValidationOptions()
        assert opts.check_images is False
        assert opts.profile is True
        assert opts.read_image_headers is True
        assert opts.top_n_anomalies == 20

    def test_frozen(self):
        from od_platform.data_validation.registry import ValidationOptions
        opts = ValidationOptions()
        import pytest
        with pytest.raises(Exception):
            opts.check_images = True  # frozen, should raise


# ---------- ValidationReport ----------

class TestValidationReport:
    def test_overall_severity(self):
        from od_platform.data_validation.registry import CheckResult, CheckSeverity
        from od_platform.data_validation.report import ValidationReport
        from od_platform.data_validation.snapshot import DatasetSnapshot
        from pathlib import Path

        snap = DatasetSnapshot(
            yaml_path=Path("/a.yaml"), yaml_data={}, yaml_load_error=None,
            data_root=Path("/"), nc=None, class_names=(),
            task_type="detect", images_per_split={}, labels_per_split={},
            stats_per_split={}, label_files_per_split={},
        )
        report = ValidationReport(
            run_id="test", yaml_path=Path("/a.yaml"), snapshot=snap,
            results=[], duration_seconds=0.5, started_at_iso="2026-01-01T00:00:00Z",
        )
        assert report.overall_severity == CheckSeverity.PASS
        assert report.exit_code == 0

    def test_exit_code_with_warning(self):
        from od_platform.data_validation.registry import CheckResult, CheckSeverity
        from od_platform.data_validation.report import ValidationReport
        from od_platform.data_validation.snapshot import DatasetSnapshot
        snap = DatasetSnapshot(
            yaml_path=Path("/a.yaml"), yaml_data={}, yaml_load_error=None,
            data_root=Path("/"), nc=None, class_names=(),
            task_type="detect", images_per_split={}, labels_per_split={},
            stats_per_split={}, label_files_per_split={},
        )
        report = ValidationReport(
            run_id="test", yaml_path=Path("/a.yaml"), snapshot=snap,
            results=[
                CheckResult(name="c1", severity=CheckSeverity.WARNING, summary="w"),
            ],
            duration_seconds=0.5, started_at_iso="2026-01-01T00:00:00Z",
        )
        assert report.exit_code == 1

    def test_exit_code_with_error(self):
        from od_platform.data_validation.registry import CheckResult, CheckSeverity
        from od_platform.data_validation.report import ValidationReport
        from od_platform.data_validation.snapshot import DatasetSnapshot
        snap = DatasetSnapshot(
            yaml_path=Path("/a.yaml"), yaml_data={}, yaml_load_error=None,
            data_root=Path("/"), nc=None, class_names=(),
            task_type="detect", images_per_split={}, labels_per_split={},
            stats_per_split={}, label_files_per_split={},
        )
        report = ValidationReport(
            run_id="test", yaml_path=Path("/a.yaml"), snapshot=snap,
            results=[
                CheckResult(name="c1", severity=CheckSeverity.ERROR, summary="e"),
            ],
            duration_seconds=0.5, started_at_iso="2026-01-01T00:00:00Z",
        )
        assert report.exit_code == 2

    def test_to_dict_keys(self):
        from od_platform.data_validation.registry import CheckSeverity, CheckResult
        from od_platform.data_validation.report import ValidationReport
        from od_platform.data_validation.snapshot import DatasetSnapshot
        snap = DatasetSnapshot(
            yaml_path=Path("/a.yaml"), yaml_data={}, yaml_load_error=None,
            data_root=Path("/"), nc=2, class_names=("a", "b"),
            task_type="detect", images_per_split={}, labels_per_split={},
            stats_per_split={}, label_files_per_split={},
        )
        report = ValidationReport(
            run_id="test", yaml_path=Path("/a.yaml"), snapshot=snap,
            results=[CheckResult(name="t", severity=CheckSeverity.PASS, summary="ok")],
            duration_seconds=0.3, started_at_iso="2026-01-01T00:00:00Z",
        )
        d = report.to_dict()
        assert "run_id" in d
        assert "overall_severity" in d
        assert "exit_code" in d
        assert "results" in d
        assert "dataset_summary" in d
