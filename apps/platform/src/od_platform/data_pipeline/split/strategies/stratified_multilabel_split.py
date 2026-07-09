"""多标签迭代分层划分策略 —— 确保所有类别(不只是主类别)在三组中分布一致。

算法: Sechidis et al. (2011) "On the Stratification of Multi-label Data"

核心思路 —— 从最稀有的类别开始迭代分配:
    1. 为每个类别计算 train/val/test 期望张数
    2. 按稀有度排序(包含该类的图数最少 → 最先处理)
    3. 对每个类别,找到"还没被分配、且含有该类"的图
    4. 把图分配给"还缺该类最多"的那个子集
    5. 最后把剩余未分配的图按容量缺口填进去

为什么这比"主类别分层"更好:
    · 主类别分层只看每张图的一个主要类别,这张图含有的次要稀有类就被忽略了
    · 迭代分层按稀有度逐个类别做,所有类都被显式照顾到
    · 尤其适合:每张图有多个不同类别的标注(目标检测场景的常态)
"""
from __future__ import annotations

import logging
from collections import Counter, defaultdict
from typing import Dict, List, Set, Tuple

from od_platform.common.constants import SplitStrategy
from od_platform.data_pipeline.split.manifest import Pair, PairList, SplitManifest
from od_platform.data_pipeline.split.strategies.common import (
    seeded_shuffled,
    validate_rates,
)
from od_platform.data_pipeline.split.strategy_registry import (
    SplitOptions,
    register_strategy,
)

logger = logging.getLogger(__name__)

# 三个子集名称
_SPLITS = ("train", "val", "test")


@register_strategy(SplitStrategy.STRATIFIED_MULTILABEL, requires_labels=True)
def stratified_multilabel_split(pairs: PairList, options: SplitOptions) -> SplitManifest:
    """迭代式多标签分层划分。

    需要 labels_per_image;如果未提供,回退到纯随机。
    """
    total = len(pairs)
    if total == 0:
        return SplitManifest(
            train_rate=options.train_rate, val_rate=options.val_rate,
            test_rate=round(1.0 - options.train_rate - options.val_rate, 4),
        )

    validate_rates(options.train_rate, options.val_rate)
    test_rate = round(1.0 - options.train_rate - options.val_rate, 4)
    ratios = {
        "train": options.train_rate,
        "val": options.val_rate,
        "test": test_rate,
    }

    labels_per_image = options.labels_per_image

    # — 回退:没有 labels 信息时按纯随机 —
    if not labels_per_image:
        logger.warning(
            "stratified_multilabel 策略需要 labels_per_image 但未提供,回退到纯随机划分"
        )
        from od_platform.data_pipeline.split.strategies.common import three_way_counts
        shuffled = seeded_shuffled(pairs, options.random_state)
        n_train, n_val, n_test = three_way_counts(total, options.train_rate, options.val_rate)
        return SplitManifest(
            train=shuffled[:n_train],
            val=shuffled[n_train:n_train + n_val],
            test=shuffled[n_train + n_val:],
            train_rate=options.train_rate,
            val_rate=options.val_rate,
            test_rate=test_rate,
        )

    # — 1. 建立"stem→图像的类集合"和"类→含有它的图像列表"的索引 —
    stem_to_classes: Dict[str, Set[str]] = {}
    class_to_stems: Dict[str, Set[str]] = defaultdict(set)
    stem_to_pair: Dict[str, Pair] = {}

    for img_path, lbl_path in pairs:
        stem = img_path.stem
        stem_to_pair[stem] = (img_path, lbl_path)
        cls_set = set(labels_per_image.get(stem, []))
        stem_to_classes[stem] = cls_set
        for c in cls_set:
            class_to_stems[c].add(stem)

    all_classes = sorted(class_to_stems.keys())
    if not all_classes:
        # 没有任何类别信息 → 纯随机
        logger.warning("labels_per_image 中没有任何类别,回退到纯随机")
        from od_platform.data_pipeline.split.strategies.common import three_way_counts
        shuffled = seeded_shuffled(pairs, options.random_state)
        n_train, n_val, n_test = three_way_counts(total, options.train_rate, options.val_rate)
        return SplitManifest(
            train=shuffled[:n_train],
            val=shuffled[n_train:n_train + n_val],
            test=shuffled[n_train + n_val:],
            train_rate=options.train_rate,
            val_rate=options.val_rate,
            test_rate=test_rate,
        )

    # — 2. 计算每个类别在各子集的期望张数 —
    desired: Dict[str, Dict[str, int]] = {}  # {class_name: {split: desired_count}}
    for c in all_classes:
        n = len(class_to_stems[c])
        desired[c] = {
            "train": max(1, round(n * ratios["train"])),
            "val": max(1, round(n * ratios["val"])),
            "test": max(1, round(n * ratios["test"])),
        }

    # — 3. 按稀有度排序(包含该类图像最少的先处理) —
    sorted_classes = sorted(all_classes, key=lambda c: len(class_to_stems[c]))

    # — 4. 迭代分配 —
    # 每个子集已收集的 stem 集合
    assigned_stems: Dict[str, Set[str]] = {s: set() for s in _SPLITS}
    # 每个子集中各类别已分配的数量
    current_counts: Dict[str, Dict[str, int]] = {s: defaultdict(int) for s in _SPLITS}
    # 所有已分配的 stem
    all_assigned: Set[str] = set()

    for cls in sorted_classes:
        # 找出含有该类、且尚未被分配的 stem
        candidates = class_to_stems[cls] - all_assigned
        if not candidates:
            continue

        candidate_list = seeded_shuffled(list(candidates), options.random_state)

        for stem in candidate_list:
            # 选择对该类别"最缺"的子集
            # 缺口 = desired - current;缺口最大的优先
            deficits = {
                s: desired[cls][s] - current_counts[s][cls]
                for s in _SPLITS
            }
            # 如果有缺口 > 0,选缺口最大的;否则选总数最少的
            best_split = max(_SPLITS, key=lambda s: (deficits[s], -len(assigned_stems[s])))

            assigned_stems[best_split].add(stem)
            all_assigned.add(stem)
            # 更新该子集中所有涉及类别的计数
            for c in stem_to_classes.get(stem, set()):
                current_counts[best_split][c] += 1

    # — 5. 分配剩余的未分配 stem —
    unassigned = set(stem_to_pair.keys()) - all_assigned
    if unassigned:
        unassigned_list = seeded_shuffled(list(unassigned), options.random_state)
        # 按容量需求分配给还缺样本的子集
        desired_totals = {
            "train": round(total * ratios["train"]),
            "val": round(total * ratios["val"]),
            "test": total - round(total * ratios["train"]) - round(total * ratios["val"]),
        }
        # 修正 test 数量
        desired_totals["train"] = total - desired_totals["val"] - desired_totals["test"]

        for stem in unassigned_list:
            # 选当前数量离目标最远的子集
            deficits = {
                s: desired_totals[s] - len(assigned_stems[s])
                for s in _SPLITS
            }
            best_split = max(_SPLITS, key=lambda s: deficits[s])
            assigned_stems[best_split].add(stem)
            for c in stem_to_classes.get(stem, set()):
                current_counts[best_split][c] += 1

    # — 6. 组装结果 —
    result: Dict[str, PairList] = {s: [] for s in _SPLITS}
    for split_name in _SPLITS:
        result[split_name] = [stem_to_pair[s] for s in assigned_stems[split_name]]
        # 组内打乱
        result[split_name] = seeded_shuffled(
            result[split_name], options.random_state + {"train": 1, "val": 2, "test": 3}[split_name],
        )

    # — 7. 打印各类在各 split 的实际占比 —
    _log_distribution(all_classes, current_counts, result, ratios)

    return SplitManifest(
        train=result["train"],
        val=result["val"],
        test=result["test"],
        train_rate=options.train_rate,
        val_rate=options.val_rate,
        test_rate=test_rate,
    )


def _log_distribution(
    all_classes: List[str],
    current_counts: Dict[str, Dict[str, int]],
    result: Dict[str, PairList],
    ratios: Dict[str, float],
) -> None:
    """打印各类在各 split 中的实际分布情况。"""
    logger.info("多标签分层完成: train=%d, val=%d, test=%d",
                 len(result["train"]), len(result["val"]), len(result["test"]))

    # 只在 DEBUG 级别输出详细分布
    if not logger.isEnabledFor(logging.DEBUG):
        return

    for cls in all_classes:
        parts = []
        for s in _SPLITS:
            total_in_split = len(result[s])
            cnt = current_counts[s].get(cls, 0)
            pct = f"{cnt / total_in_split * 100:.1f}%" if total_in_split else "0%"
            parts.append(f"{s}={cnt}({pct})")
        logger.debug("  %s: %s (期望 %.0f%%/%.0f%%/%.0f%%)",
                      cls, " ".join(parts),
                      ratios["train"] * 100, ratios["val"] * 100, ratios["test"] * 100)
