#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :refs.py
# @Time      :2026/7/1 15:11:56
# @Author    :雨霓同学
# @Project   :ODPlatform
# @Function  :引用解析：把命令行用户给dataset / yaml / model /等等名字或者路径统一做好解析，解析成统一的path
"""
对于数据集来说：用户可能传：--dataset rsod 或者 --dataset /path/to/rsod
对于模型来说：用户可能传：--model resnet50 或者 --model /path/to/resnet50
对于配置来说：用户可能传：--config config.yaml 或者 --config /path/to/config.yaml
对于其他资源来说：用户可能传：--resource name 或者 --resource /path/to/resource
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional
from od_platform.common.paths import (
    DATASET_CONFIGS_DIR,
    PRETRAINED_MODELS_DIR,
    RAW_DATA_DIR,
    TRAINED_MODELS_DIR,
)


def resolve_ref(ref: str, *, base_dir: Path, default_suffix: Optional[str] = None) -> Path:
    p = Path(ref)
    if p.is_absolute() or len(p.parts) > 1:
        return p.resolve()
    name = ref if (not default_suffix or ref.endswith(default_suffix)) else ref + default_suffix
    return (base_dir / name).resolve()


def resolve_dataset(ref: str) -> Path:
    return resolve_ref(ref, base_dir=RAW_DATA_DIR)


def resolve_pretrained_model(ref: str) -> Path:
    """解析预训练权重名/路径 → 绝对路径。找不到时返回裸名(由 ultralytics 下载兜底)。"""
    p = Path(ref)
    if p.is_absolute():
        return p.resolve()
    if p.exists():
        return p.resolve()
    name = ref if ref.endswith(".pt") else f"{ref}.pt"
    candidate = (PRETRAINED_MODELS_DIR / name).resolve()
    if candidate.exists():
        return candidate
    # 找不到则返回 Path(ref),由调用方决定是否让 ultralytics 下载
    return Path(ref)


def resolve_trained_model(ref: str) -> Path:
    """解析已训练权重名/路径 → 绝对路径。纯解析,不下载。"""
    p = Path(ref)
    if p.is_absolute():
        return p.resolve()
    if p.exists():
        return p.resolve()
    name = ref if ref.endswith(".pt") else f"{ref}.pt"
    return (TRAINED_MODELS_DIR / name).resolve()


def resolve_yaml(ref: str) -> Path:
    """解析数据集 yaml 名/路径 → 绝对路径。"""
    return resolve_ref(ref, base_dir=DATASET_CONFIGS_DIR, default_suffix=".yaml")

