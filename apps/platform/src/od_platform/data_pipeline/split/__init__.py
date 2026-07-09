"""split 子系统 —— train/val/test 划分 + 物化 + yaml 生成。"""
from od_platform.data_pipeline.split.manifest import (
    Pair as Pair,
    PairList as PairList,
    SplitManifest as SplitManifest,
    build_manifest as build_manifest,
)
from od_platform.data_pipeline.split.materializer import (
    SplitOutputDirs as SplitOutputDirs,
    materialize as materialize,
)
from od_platform.data_pipeline.split.split_service import (
    split_pairs as split_pairs,
)
from od_platform.data_pipeline.split.strategy_registry import (
    SplitOptions as SplitOptions,
    available_strategies as available_strategies,
    register_strategy as register_strategy,
)
from od_platform.data_pipeline.split.yaml_writer import (
    write_dataset_yaml as write_dataset_yaml,
)

__all__ = [
    "Pair",
    "PairList",
    "SplitManifest",
    "build_manifest",
    "SplitOutputDirs",
    "materialize",
    "split_pairs",
    "SplitOptions",
    "available_strategies",
    "register_strategy",
    "write_dataset_yaml",
]
