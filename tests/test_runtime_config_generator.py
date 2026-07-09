"""运行配置生成器测试。"""
from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "apps" / "platform" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


class _FakeConfig:
    @classmethod
    def get_field_groups(cls):
        return {"基础": ["epochs"]}

    @classmethod
    def model_construct(cls):
        return cls()

    def get_field_groups(self):
        return {"基础": ["epochs"]}

    def get_field_metadata(self, name):
        return {
            "yaml_comment": "训练轮数",
            "examples": [100],
            "tips": ["必须为正整数"],
            "default": 10,
        }


def test_generate_supports_dry_run(tmp_path, capsys):
    from od_platform.runtime_config.generator import ConfigGenerator

    output = tmp_path / "train.yaml"
    ok = ConfigGenerator().generate(_FakeConfig, output, title="测试配置", dry_run=True)
    captured = capsys.readouterr()

    assert ok is True
    assert "测试配置" in captured.out
    assert output.exists() is False


def test_main_supports_custom_name(monkeypatch, tmp_path, capsys):
    from od_platform.runtime_config import generator as gen

    monkeypatch.setattr(gen, "CONFIG_REGISTRY", {"train": (_FakeConfig, "测试配置")})
    monkeypatch.setattr(gen, "runtime_config_path", lambda name: tmp_path / f"{name}.yaml")

    gen.main(["train", "--name", "train_demo"])
    captured = capsys.readouterr()

    assert "[OK] 已生成:" in captured.out
    assert (tmp_path / "train_demo.yaml").exists()
