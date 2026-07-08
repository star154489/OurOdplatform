"""training 子系统 —— 编排 D4/D5/ultralytics 完成 YOLO 训练。"""
from od_platform.training.service import (
    TrainService as TrainService,
    TrainResult as TrainResult,
    train_yolo as train_yolo,
)

__all__ = ["TrainService", "TrainResult", "train_yolo"]
