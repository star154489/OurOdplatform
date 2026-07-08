"""项目级共享常量——所有模块的"共同词汇表"。
放这里的标准:多模块共享(>=2 处用到) + 纯定义无逻辑 + 极少改动。本文件按需增长。
"""
from __future__ import annotations
from typing import Tuple


# —— 标注格式名(阶段 2:@register 要用,且会在多个 converter/CLI/测试复用)——
class AnnotationFormat:
    PASCAL_VOC = "pascal_voc"
    COCO       = "coco"
    YOLO       = "yolo"
    @classmethod
    def all(cls) -> Tuple[str, ...]:
        return cls.PASCAL_VOC, cls.COCO, cls.YOLO

# —— 任务类型(同上)——
class Task:
    DETECT  = "detect"
    SEGMENT = "segment"
    @classmethod
    def all(cls) -> Tuple[str, ...]:
        return cls.DETECT, cls.SEGMENT

DEFAULT_RANDOM_STATE = 1210

# —— 浮点容差(阶段 4)————————————————————————————————————————————
# 1.0 - 0.7 - 0.3 在浮点里不是 0,而是 5.55e-17。校验 test_rate >= 0 时用它吸收这种误差,
# 否则正常的 70/30 切分会被误判成"比例越界"。
RATE_EPSILON = 1e-6

class SplitStrategy:
    """train/val/test 划分策略名(阶段 4 随着撞墙②逐个长出来)。"""
    RANDOM = "random"                          # 纯随机:对稀有类不公平
    STRATIFIED = "stratified"                  # 主类别分层:稀有类不至于整体消失
    STRATIFIED_MULTILABEL = "stratified_multilabel"  # 多标签分层:连次要稀有类也照顾

    @classmethod
    def all(cls) -> Tuple[str, ...]:
        return cls.RANDOM, cls.STRATIFIED, cls.STRATIFIED_MULTILABEL

# —— 默认值(阶段 4)————————————————————————————————————————————————
DEFAULT_SPLIT_STRATEGY = SplitStrategy.RANDOM   # 不指定 --split-strategy 时的默认

# —— 类别平衡报告的判级阈值(阶段 5)——————————————————————————————
CLASS_MIN_IMAGES_HARD = 2     # 某类图数低于此,怎么分都进不全 train/val/test
CLASS_MIN_BOXES_WARN = 20     # 框数低于此,样本太少大概率学不好
CLASS_MIN_BOX_SHARE = 0.01    # 框占比低于 1%,相对其它类严重偏少

# —— 图像-标注覆盖率阈值(阶段 6,fail-fast)——————————————————————
COVERAGE_HARD_THRESHOLD = 0.5   # 低于此:数据明显残缺,直接终止(别让训练白干)
COVERAGE_SOFT_THRESHOLD = 0.9   # 低于此:仅警告,允许继续

# —— 认识哪些图像扩展名(阶段 7,配对图与标注时用)————————————————
# 只认 .jpg 会把 png/jpeg 的数据静默丢光,所以这里列全;新增格式往这里加即可。
IMAGE_EXTENSIONS: Tuple[str, ...] = (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp")

# ============================================================
# D4 增量: 数据验证 (data_validation 子系统)
# ============================================================

# ---- pair_existence 缺失比例分级 ----
PAIR_MISSING_ERROR_RATIO: float = 0.5   # >= 50%: ERROR (流程级问题)
PAIR_MISSING_WARN_RATIO:  float = 0.05  # 5% ~ 50%: WARNING

# ---- annotation_coverage 无标注图比例分级 ----
UNLABELED_INFO_RATIO:  float = 0.05   # >= 5%: INFO
UNLABELED_WARN_RATIO:  float = 0.30   # >= 30%: WARNING

# ---- bbox_within_image 出图检测 ----
BBOX_EDGE_TOLERANCE: float = 1e-6     # 吞浮点尾差, 不把数值噪声当事故
BBOX_OUT_ERROR_RATIO: float = 0.10    # 出图占比 >= 10%: ERROR (系统性错误)

# ---- box_geometry 退化框 ----
DEGENERATE_BOX_MIN_SIZE: float = 1e-3  # 归一化宽/高低于此 = 退化 (640px 图 ≈ 0.64px)

# ---- 小目标双口径 (归一化口径) ----
SMALL_OBJECT_AREA_RATIO: float = 0.001  # 归一化面积 < 0.001 视为小目标

# ---- 极端宽高比 (D3 孤儿常量, D4 首次消费者) ----
STATS_MAX_ASPECT_RATIO: float = 20  # w/h 或 h/w 超过此值视为极端

# ---- duplicate_annotations 近重复 IoU 阈值 ----
DUPLICATE_BOX_IOU_THRESHOLD: float = 0.95  # 同图同类 IoU >= 此值视为近重复

# ---- class_balance 失衡比阈值 ----
IMBALANCE_WARN_RATIO: float = 20   # 失衡比 >= 20x: INFO
IMBALANCE_ERROR_RATIO: float = 50  # 失衡比 >= 50x: WARNING

# ---- class_presence 类别出现性 ----
STRAY_CLASS_WARN_RATIO: float = 0.01    # 孤立实例占同类实例比 < 1% 时忽略
STRAY_CLASS_MIN_IMAGES: int = 2         # 某类别至少需要的图像数
CLASS_MIN_IMAGES_HARD: int = 5          # 某类图数低于此 = 样本太少
CLASS_MIN_BOXES_WARN: int = 50          # 框数低于此 = 样本太少大概率学不好
CLASS_MIN_BOX_SHARE: float = 0.005      # 框占比低于 0.5%, 相对其它类严重偏少

# ---- 覆盖硬阈值 (D3 遗留消费者) ----
COVERAGE_HARD_THRESHOLD: float = 0.5     # 低于此: 数据明显残缺, 直接终止
COVERAGE_SOFT_THRESHOLD: float = 0.9     # 低于此: 仅警告, 允许继续

# ---- 分布一致性 (JSD 阈值) ----
DIST_JSD_MINOR: float = 0.05            # JSD < 0.05 = 一致
DIST_JSD_MAJOR: float = 0.15            # JSD >= 0.15 = 显著偏差
DIST_SHARE_DEVIATION_PP: float = 5.0    # 单类占比差 > 5 个百分点单独标记

# ---- 边框贴边阈值 (profiler 用) ----
BORDER_TOUCH_EPS: float = 0.02          # 边框距图像边缘 < 2% 视为贴边

# ---- EXIF 方向码 (image_integrity 用) ----
EXIF_ORIENTATION_CODES: Tuple[int, ...] = (3, 6, 8)

# ---- 图像损坏 ERROR 阈值 ----
IMAGE_CORRUPT_ERROR_RATIO: float = 0.10  # 损坏占比 >= 10%: ERROR

# ---- 渲染缩进 ----
RENDER_INDENT: int = 2
