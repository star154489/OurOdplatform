"""ODPlatform 数据流水线(data_pipeline) —— 原始标注 → 可训练数据集。

提供:
  - convert:    标注格式转换(VOC/COCO/YOLO → YOLO txt)
  - split:      划分(train/val/test) + 落盘 + yaml 生成
  - report:     类别平衡报告
  - orchestrator: 全流程编排器 DatasetPipeline
"""
from od_platform.data_pipeline.convert.registry import (
    ConvertOptions as ConvertOptions,
    available_formats as available_formats,
    get_converter as get_converter,
    register as register,
)
from od_platform.data_pipeline.convert.service import (
    convert_data_to_yolo as convert_data_to_yolo,
)
from od_platform.data_pipeline.orchestrator import DatasetPipeline as DatasetPipeline
from od_platform.data_pipeline.report import (
    ClassBalanceReport as ClassBalanceReport,
    ClassStat as ClassStat,
    analyze_class_balance as analyze_class_balance,
)
from od_platform.data_pipeline.split.manifest import (
    Pair as Pair,
    PairList as PairList,
    SplitManifest as SplitManifest,
    build_manifest as build_manifest,
)
from od_platform.data_pipeline.split.split_service import split_pairs as split_pairs
from od_platform.data_pipeline.split.strategy_registry import (
    SplitOptions as SplitOptions,
    available_strategies as available_strategies,
)

__all__ = [
    # orchestrator
    "DatasetPipeline",
    # report
    "ClassBalanceReport",
    "ClassStat",
    "analyze_class_balance",
    # convert
    "ConvertOptions",
    "get_converter",
    "available_formats",
    "register",
    "convert_data_to_yolo",
    # split
    "SplitOptions",
    "available_strategies",
    "split_pairs",
    "SplitManifest",
    "Pair",
    "PairList",
    "build_manifest",
]
